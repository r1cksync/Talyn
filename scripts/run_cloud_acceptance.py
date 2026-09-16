"""Launch the bounded synthetic acceptance runner inside Talyn's AWS network.

Operator credentials stay in memory. A separate simulator-only Cognito identity is
injected through Secrets Manager; no password or invitation token is printed.
"""

import argparse
import copy
import csv
import json
import secrets
import time
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credential-csv", required=True)
    parser.add_argument("--region", default="ap-south-1")
    args = parser.parse_args()
    with open(args.credential_csv, encoding="utf-8-sig") as handle:
        row = next(csv.DictReader(handle))
    session = boto3.Session(
        aws_access_key_id=row["Access key ID"],
        aws_secret_access_key=row["Secret access key"],
        region_name=args.region,
    )
    stack = session.client("cloudformation").describe_stacks(StackName="TalynFoundation")["Stacks"][0]
    outputs = {v["OutputKey"]: v["OutputValue"] for v in stack["Outputs"]}
    ecs, iam, cognito, sm = [session.client(name) for name in ("ecs", "iam", "cognito-idp", "secretsmanager")]
    service = ecs.describe_services(cluster=outputs["Cluster"], services=[outputs["ApiService"]])["services"][0]
    definition = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    email = "success@simulator.amazonses.com"
    password = secrets.token_urlsafe(32) + "aA1!"
    try:
        cognito.admin_create_user(
            UserPoolId=outputs["CognitoPool"],
            Username=email,
            MessageAction="SUPPRESS",
            UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
        )
    except cognito.exceptions.UsernameExistsException:
        pass
    cognito.admin_set_user_password(
        UserPoolId=outputs["CognitoPool"], Username=email, Password=password, Permanent=True
    )
    payload = json.dumps({"email": email, "password": password})
    try:
        secret = sm.create_secret(
            Name="talyn/acceptance-credentials", SecretString=payload, Tags=[{"Key": "Project", "Value": "talyn"}]
        )["ARN"]
    except sm.exceptions.ResourceExistsException:
        secret = sm.put_secret_value(SecretId="talyn/acceptance-credentials", SecretString=payload)["ARN"]
    role = definition["executionRoleArn"].rsplit("/", 1)[-1]
    iam.put_role_policy(
        RoleName=role,
        PolicyName="TalynSyntheticAcceptanceSecret",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Action": "secretsmanager:GetSecretValue", "Resource": secret}],
            }
        ),
    )
    fields = (
        "taskRoleArn",
        "executionRoleArn",
        "networkMode",
        "containerDefinitions",
        "volumes",
        "requiresCompatibilities",
        "cpu",
        "memory",
        "runtimePlatform",
        "ephemeralStorage",
    )
    task = {key: copy.deepcopy(definition[key]) for key in fields if key in definition}
    task["family"] = "talyn-synthetic-acceptance"
    container = task["containerDefinitions"][0]
    container["command"] = ["python", "-m", "app.cloud_smoke"]
    container["environment"].append({"name": "TALYN_ACCEPTANCE_RUN", "value": "synthetic"})
    container["secrets"].append({"name": "TALYN_SMOKE_CREDENTIALS", "valueFrom": secret})
    container.pop("healthCheck", None)
    container["portMappings"] = []
    registered = ecs.register_task_definition(**task, tags=[{"key": "Project", "value": "talyn"}])["taskDefinition"]
    started = ecs.run_task(
        cluster=outputs["Cluster"],
        taskDefinition=registered["taskDefinitionArn"],
        launchType="FARGATE",
        networkConfiguration=service["networkConfiguration"],
        count=1,
        startedBy="talyn-synthetic-acceptance",
        tags=[{"key": "Project", "value": "talyn"}],
    )
    if started.get("failures"):
        raise RuntimeError("ECS could not start the synthetic acceptance task")
    arn = started["tasks"][0]["taskArn"]
    print(json.dumps({"task": arn, "url": outputs["ApplicationUrl"]}), flush=True)
    logs = session.client("logs")
    options = container["logConfiguration"]["options"]
    stream = f"{options['awslogs-stream-prefix']}/{container['name']}/{arn.rsplit('/', 1)[-1]}"
    next_token = None
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        state = ecs.describe_tasks(cluster=outputs["Cluster"], tasks=[arn])["tasks"][0]
        try:
            params = {"logGroupName": options["awslogs-group"], "logStreamName": stream, "startFromHead": True}
            if next_token:
                params["nextToken"] = next_token
            events = logs.get_log_events(**params)
            next_token = events["nextForwardToken"]
            for event in events["events"]:
                print(event["message"], flush=True)
        except logs.exceptions.ResourceNotFoundException:
            pass
        if state["lastStatus"] == "STOPPED":
            result = {
                "task": arn,
                "exit_code": state["containers"][0].get("exitCode"),
                "reason": state.get("stoppedReason"),
                "url": outputs["ApplicationUrl"],
            }
            path = Path(__file__).resolve().parents[1] / ".local/cloud-acceptance-result.json"
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result), flush=True)
            raise SystemExit(0 if result["exit_code"] == 0 else 1)
        time.sleep(15)
    ecs.stop_task(cluster=outputs["Cluster"], task=arn, reason="Synthetic acceptance exceeded its 20-minute bound")
    raise RuntimeError("Synthetic acceptance timed out")


if __name__ == "__main__":
    main()
