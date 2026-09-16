"""Read-only AWS discovery plus optional bounded synthetic provider calls. No secrets are printed."""
import argparse
import asyncio
import csv
import json
import os
from pathlib import Path

import boto3
from botocore.config import Config

parser = argparse.ArgumentParser()
parser.add_argument("--credential-csv", type=Path)
parser.add_argument("--region", default="ap-south-1")
parser.add_argument("--smoke", action="store_true")
parser.add_argument("--pricing", action="store_true")
parser.add_argument("--output", type=Path, default=Path("../docs/aws-preflight.json"))
args = parser.parse_args()
if args.credential_csv:
    with args.credential_csv.open(encoding="utf-8-sig") as handle:
        credentials = next(csv.DictReader(handle))
    os.environ["AWS_ACCESS_KEY_ID"] = credentials["Access key ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = credentials["Secret access key"]
os.environ["AWS_DEFAULT_REGION"] = args.region
config = Config(connect_timeout=5, read_timeout=45, retries={"max_attempts": 2})
client = lambda service, region=None: boto3.client(service, region_name=region or args.region, config=config)
output = {"region": args.region, "checks": {}, "resources_created": []}


def check(name, function):
    try:
        output["checks"][name] = {"status": "passed", "result": function()}
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
        output["checks"][name] = {"status": "blocked", "error_code": code}
    print(name, output["checks"][name]["status"])


check("principal", lambda: {"is_root": client("sts").get_caller_identity()["Arn"].endswith(":root")})
check("ses", lambda: {k: v for k, v in client("sesv2").get_account().items() if k in {"ProductionAccessEnabled", "SendingEnabled", "SendQuota"}})
check("ses_identities", lambda: [{"identity": i["IdentityName"], "verified": i["VerifiedForSendingStatus"]} for i in client("sesv2").list_email_identities()["EmailIdentities"]])
check("certificates", lambda: [{"domain": i["DomainName"], "status": i.get("Status")} for i in client("acm").list_certificates()["CertificateSummaryList"]])
check("domains", lambda: [z["Name"] for z in client("route53").list_hosted_zones()["HostedZones"]])
check("model_profile", lambda: {"status": client("bedrock").get_inference_profile(inferenceProfileIdentifier="apac.amazon.nova-lite-v1:0")["status"]})
for code in ["fargate", "transcribe", "bedrock"]:
    check("quotas_"+code, lambda code=code: [{"name": q["QuotaName"], "value": q["Value"]} for page in client("service-quotas").get_paginator("list_service_quotas").paginate(ServiceCode=code) for q in page["Quotas"] if (code=="fargate" or "stream" in q["QuotaName"].lower() or "Nova Lite" in q["QuotaName"])])

if args.smoke:
    def bedrock():
        result = client("bedrock-runtime").converse(modelId="apac.amazon.nova-lite-v1:0",
            messages=[{"role":"user","content":[{"text":"Return exactly the word READY. This is a synthetic connectivity test."}]}],
            inferenceConfig={"maxTokens": 10, "temperature": 0})
        return {"returned_text": result["output"]["message"]["content"][0]["text"], "usage": result["usage"]}
    check("bedrock_converse", bedrock)
    def polly():
        result = client("polly").synthesize_speech(Text="This is a synthetic Talyn connection test.", VoiceId="Joanna", Engine="neural", OutputFormat="pcm", SampleRate="16000")
        with result["AudioStream"] as stream:
            audio = stream.read()
        return audio
    synthesized = None
    try:
        synthesized = polly()
        output["checks"]["polly"] = {"status": "passed", "result": {"pcm_bytes": len(synthesized)}}
        print("polly passed")
    except Exception as exc:
        output["checks"]["polly"] = {"status": "blocked", "error_code": getattr(exc,"response",{}).get("Error",{}).get("Code",type(exc).__name__)}
    async def transcribe():
        from amazon_transcribe.client import TranscribeStreamingClient
        from amazon_transcribe.handlers import TranscriptResultStreamHandler
        received=[]
        stream=await TranscribeStreamingClient(region=args.region).start_stream_transcription(language_code="en-US",media_sample_rate_hz=16000,media_encoding="pcm")
        class Handler(TranscriptResultStreamHandler):
            async def handle_transcript_event(self,event):
                for result in event.transcript.results:
                    if not result.is_partial and result.alternatives:
                        received.append(result.alternatives[0].transcript)
        async def send():
            audio=synthesized or bytes(64000)
            for offset in range(0,len(audio),3200):
                await stream.input_stream.send_audio_event(audio_chunk=audio[offset:offset+3200])
                await asyncio.sleep(.1)
            await stream.input_stream.end_stream()
        await asyncio.wait_for(asyncio.gather(send(),Handler(stream.output_stream).handle_events()),30)
        if synthesized and not received:
            raise ValueError("No final transcript received")
        return {"final_segments":len(received),"synthetic_transcript":received}
    check("transcribe_streaming", lambda:asyncio.run(transcribe()))

if args.pricing:
    pricing=client("pricing","us-east-1")
    rates=[]
    for service,filters in [
        ("AmazonECS",[]),
        ("AmazonRDS",[("instanceType","db.t4g.micro"),("databaseEngine","PostgreSQL"),("deploymentOption","Single-AZ")]),
        ("AWSELB",[]),
        ("AmazonTranscribe",[]),
        ("AmazonPolly",[]),
        ("AmazonRekognition",[]),
    ]:
        try:
            result=pricing.get_products(ServiceCode=service,Filters=[{"Type":"TERM_MATCH","Field":"location","Value":"Asia Pacific (Mumbai)"}]+[{"Type":"TERM_MATCH","Field":k,"Value":v} for k,v in filters],MaxResults=100)
            for item in result["PriceList"]:
                data=json.loads(item)
                attr=data["product"]["attributes"]
                for term in data["terms"].get("OnDemand",{}).values():
                    for price in term["priceDimensions"].values():
                        if float(price["pricePerUnit"]["USD"])>0:
                            rates.append({"service":service,"usage":attr.get("usagetype"),"description":price["description"],"unit":price["unit"],"usd":price["pricePerUnit"]["USD"],"begin":price["beginRange"],"end":price["endRange"]})
        except Exception as exc:
            print("pricing",service,type(exc).__name__)
    output["regional_rates"]=rates
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(output,indent=2),encoding="utf-8")
print("Saved sanitized preflight results to",args.output)
