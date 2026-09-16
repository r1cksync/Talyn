# Deployment and operations

Target: `talyn`, Mumbai (`ap-south-1`). Only an SES sender identity has been created for verification; compute/storage infrastructure is not deployed. Read [blockers](aws-blockers.md) and [costs](costs.md) first. Expected baseline: roughly US$110–135/month; US$150 is an alert, not a spending cap.

## Prerequisites

1. Selected provider: **Groq**, explicitly authorized after Bedrock returned `NOT_AUTHORIZED`. Its key is in Secrets Manager. A complete synthetic workflow with real Groq inference passed. For the optional Bedrock provider, first resolve account access and run Converse successfully.
2. The user has no domain. Default deployment uses an AWS-generated `https://...cloudfront.net` address and a private ALB VPC origin. Browser traffic uses HTTPS; HTTP from CloudFront to the ALB stays on AWS's private VPC-origin connection. No domain purchase or ACM validation is needed. An existing custom domain/certificate remains optional. Verify the SES sender in Mumbai; sandbox recipients must also be verified or use the simulator.
3. Choose a monitored alert email and confirm its SNS subscription. Enable the `Project` cost allocation tag in Billing so the tagged budget receives costs; reporting can lag. Review account-wide costs separately.
4. Use an authorized temporary deployment identity, AWS CLI, Node 22, Docker, Python 3.12 and uv. Credentials stay outside the repository. Runtime uses task roles; GitHub uses OIDC. Never add administrator keys to GitHub or containers.

The reviewed plan creates a VPC with two public and two isolated subnets, S3 gateway endpoint, no NAT, private PostgreSQL 16 t4g.micro, encrypted private versioned S3, queues/DLQ, Secrets Manager, KMS, Cognito, two ECR repositories, an ECS cluster and three small Fargate services, CloudFront HTTPS with a private ALB, SES event configuration, maintenance schedule, logs, alarms and an OIDC role. The development database is single AZ. Tasks have public egress IPs; only the ALB security group reaches application ports. CloudFront caching is disabled and cookies/Origin/WebSocket headers are forwarded. Origin ingress permits only the AWS-managed CloudFront prefix list. A custom domain plus regional certificate instead selects the original public HTTPS ALB design.

## First deployment

Use bash examples below with your actual non-secret values. PowerShell users can pass the same arguments on one line and use `$env:` for environment variables.

```sh
export AWS_REGION=ap-south-1
export TALYN_SENDER_EMAIL=your-verified-email@example.com
export TALYN_ALERT_EMAIL=your-alert-email@example.com
cd infra
npm ci
npm run build && npm test
npx cdk bootstrap aws://YOUR_ACCOUNT/ap-south-1
npx cdk diff TalynFoundation -c "alertEmail=$TALYN_ALERT_EMAIL"
npx cdk deploy TalynFoundation -c "alertEmail=$TALYN_ALERT_EMAIL" --outputs-file foundation-outputs.json
```

This first stage creates foundation resources without runtime. It already incurs RDS charges. If the account already has a GitHub OIDC provider, pass `-c githubOidcProviderArn=...` on **every** deployment; do not duplicate or alter an unrelated provider. CDK bootstrap gives CloudFormation broad deployment authority; protect main and workflow permissions accordingly.

Configure repository **variables**: `TALYN_AWS_ROLE_ARN` from foundation outputs, `TALYN_SENDER_EMAIL`, `TALYN_ALERT_EMAIL`, `TALYN_LLM_PROVIDER=groq` and `TALYN_GROQ_SECRET_ARN`. Leave domain/certificate variables empty for CloudFront. These are identifiers, not keys. For manual runtime deployment, pass `-c llmProvider=groq -c groqSecretArn=YOUR_SECRET_ARN`. Otherwise Bedrock is the default.

Run **Verify Talyn** successfully on the chosen main commit, then dispatch **Deploy Talyn development**. It builds commit-tagged images, pushes to immutable ECR and deploys the stack with `-c runtime=true`. The `ApplicationUrl` output is the generated HTTPS address. CloudFront/VPC origin activation can take several minutes; no user DNS change is needed. For the optional custom-domain path, set both domain/certificate variables and point DNS to the ALB. Existing immutable image tags are reused on reruns.

Backend startup runs migrations and checkpoint initialization under a PostgreSQL advisory lock. Production rejects demo adapters. Development SES permits only the sender and simulator by default. To use another verified recipient, change `TALYN_EMAIL_ALLOWLIST` in CDK and redeploy. Enable `TALYN_LIVE_EMAIL` deliberately only after production approval and recipient review.

The free Groq pilot allows two concurrent interviews per organization. Ten concurrent local deterministic tests do not guarantee free provider capacity. Oversized prompts fail explicitly; quota retries are bounded. Run `uv run python ../scripts/groq_smoke.py --credential-csv PATH_TO_LOCAL_CSV` from backend to test real Groq inference with local synthetic storage/email fixtures.

## Live acceptance

Verify HTTPS health, Cognito signup/verification, two-tenant isolation, signed S3 checksums, a scanned synthetic PDF through Textract, Bedrock plan/evidence validation, one browser PCM → Transcribe → Polly interview, SQS retries, S3 clips, Rekognition frames and SES simulator delivery/bounce/complaint events. Confirm alarms and budget subscriptions. Repeat ten concurrent live sessions with bounded fixtures and report actual latency/cost before claiming cloud capacity. These deployed checks have not run.

## Rollback and recovery

ECS circuit breakers roll back unhealthy deployments. To roll back application code, redeploy the previous known-good ECR SHA with identical domain/certificate/sender/alert contexts. Keep database changes compatible. Do not automatically downgrade customer data; snapshot first and prefer a forward corrective migration.

RDS keeps automated backups seven days. Restore a snapshot or point-in-time backup to a **new private database**, preserve TLS and security groups, verify migrations/tenant/report/media links, then switch the stack's database reference deliberately. Rehearse this before production. S3 versions protect accidental overwrites; application deletion intentionally removes all associated versions. Database backups can retain deleted records until expiration; manual snapshots persist until removed. Cognito identities and organization membership are separate from application deletion.

## Stop and cleanup

Local: `docker compose stop` preserves database/media volumes. No automatic deletion occurs.

AWS: inventory only `TalynFoundation` / `Project=talyn` resources, export needed data and review the resource plan first. RDS deletion protection intentionally blocks teardown. S3, ECR, Cognito, KMS, secrets and logs can be retained after stack deletion and require separate deliberate cleanup. Check backup expiration and retained resource charges. Never run blanket account cleanup. No unrelated resources were modified or deleted.
