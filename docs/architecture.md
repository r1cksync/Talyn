# ADR 001 — AWS interview application

Status: implemented. Project: `talyn`. Region: `ap-south-1`.

## Authorized changes during implementation

The user has no domain and authorized an AWS-generated test address. CloudFront terminates public HTTPS and connects privately through a VPC origin to an internal ALB. Caching is disabled; cookies and WebSocket headers are forwarded. No domain purchase is needed. The original public HTTPS ALB path remains available with a custom domain/certificate.

The AWS account rejects Bedrock even with root credentials. The user explicitly selected Groq and supplied its key, overriding the original AWS-only LLM restriction. Only structured LLM requests go to Groq; runtime, documents, database, speech, media and email remain on AWS. Secrets Manager holds the key and ECS injects it only into API/worker tasks. Candidate consent version `2026-09-v2-groq` discloses this external processing. The development pilot is limited to two concurrent interviews per organization for free-tier testing.

Sources: [CloudFront VPC origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html), [Groq limits](https://console.groq.com/docs/rate-limits), [Groq structured outputs](https://console.groq.com/docs/structured-outputs), [Groq data policy](https://console.groq.com/docs/your-data).

## Decisions

* One origin routes `/api/*` to FastAPI and everything else to Next.js through an HTTPS ALB. HttpOnly manager and candidate cookies are distinct; mutation requests check Origin and a CSRF header. Invitation secrets live in URL fragments, then exchange for an email verification challenge.
* SQLAlchemy models and Alembic migrations define the application schema. All tenant entities carry `org_id`; authorization joins authenticated membership to the requested organization. Candidate sessions expose only their own application. Workers reload ownership from durable jobs.
* LangGraph runs inside Python services. PostgreSQL checkpoints in AWS and SQLite checkpoints locally share tenant-prefixed thread names. Graph nodes validate structured model outputs; an outbox owns external side effects.
* A deterministic local adapter exercises the workflow without AWS. Production rejects demo mode. Demo speech input is explicitly synthetic. AWS mode uses Bedrock Converse, Polly, and real Transcribe Streaming.
* Browser AudioWorklet produces 16 kHz mono signed 16-bit PCM, streamed through an authenticated backend WebSocket. Half-duplex turns disable capture during interviewer playback. Final segments and server deadlines persist in PostgreSQL.
* Video is recorded as independently playable short clips by stopping/restarting MediaRecorder. Each clip is checksum-verified and ordered in a manifest. Playback advances through clips; chunks are never blindly concatenated. Gaps at clip boundaries are disclosed and measured.
* Frame sampling produces only neutral observations, separate from assessments. No identity matching, sensitive-attribute inference, misconduct classifier, or automatic hiring decision.
* Development uses two public application subnets with public task IPs (inbound only from ALB), isolated private RDS, and no NAT gateway. Private S3, TLS, KMS, and scoped task roles protect data. Production can add private endpoints/NAT and multi-AZ database.
* GitHub Actions assumes an AWS role with OIDC. Root/admin keys are never copied to containers, GitHub, or project configuration.

## Milestones

1. Foundation, authentication, tenancy, schema, reproducible local setup.
2. Jobs, CSV/documents, preparation graph, editable plan/rubric.
3. Campaigns, transactional notifications, invitations and scoped candidate sessions.
4. Durable interview graph, PCM streaming, captions and Polly.
5. Incremental recording, observation timeline and accommodations.
6. Evidence-checked evaluation, separated reports, retention and operations.
7. CDK, OIDC workflows, synthetic E2E and bounded concurrency checks, deployment when configuration permits.

## Data flow

Manager → Cognito → session → tenant API → PostgreSQL/outbox → SQS → worker → LangGraph/Bedrock → approved plan.

Candidate invitation → email verification → candidate session → consent/device check → PCM WebSocket → Transcribe → durable transcript → evaluation graph → separately authorized reports → SES notifications.

Browser → short-lived signed S3 upload → server validation → document/recording records. Sampled frames → Rekognition DetectFaces with default attributes → neutral, temporally filtered observations. Video signals never enter competency scoring prompts.

## Verification sources

* [Transcribe streaming formats and chunk sizing](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html)
* [Python streaming SDK example](https://docs.aws.amazon.com/transcribe/latest/dg/getting-started-sdk.html)
* [Bedrock Nova Converse](https://docs.aws.amazon.com/nova/latest/userguide/using-converse-api.html)
* [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

Observed AWS preflight: supplied principal is account root; SES sandbox, sending enabled, quota 200/day and 1/second; no SES identities or ACM certificates in proposed region. Nova Lite is listed with inference-profile support. Live model access still requires verification.
