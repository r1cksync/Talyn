# Development resource plan and cost assumptions

Historical deployment estimate, updated 16 September 2026. Region `ap-south-1` (Mumbai). Project tag `Project=talyn`. The AWS runtime was retired on 17 September 2026; the estimates below are not current running infrastructure. See [teardown](teardown.md) for preserved S3 storage, its encryption-key dependency and charges already accrued. Historical runtime/acceptance status is in [STATUS](STATUS.md).

## Concrete resource plan

* One VPC across two availability zones, two public application subnets, two isolated database subnets, an S3 gateway endpoint. **Zero NAT gateways.**
* Three on-demand Linux/x86 Fargate tasks: API 0.5 vCPU/1 GiB; worker 0.5 vCPU/1 GiB; web 0.25 vCPU/0.5 GiB. 1.25 vCPU and 2.5 GiB total. Rolling deployments temporarily overlap tasks.
* Selected ingress: one t2.micro nginx gateway with 8 GiB encrypted gp3, one Elastic IP and trusted IP TLS certificate, forwarding to a private ALB. CloudFront is account-blocked. The optional custom-domain path uses a public HTTPS ALB. Tasks accept inbound application traffic only from the ALB.
* One private, encrypted, single-AZ RDS PostgreSQL 16 `db.t4g.micro`, 20 GiB gp3 (30 GiB maximum autoscaling), seven-day automatic backups and deletion protection.
* One private versioned KMS-encrypted S3 media bucket; short-lived scoped upload/download URLs. One KMS key and Secrets Manager secrets for database/session credentials, the authorized Groq key and simulator-only acceptance credentials.
* Two ECR repositories; Cognito user pool/client; job queue, email-event queue and dead-letter queue; SES configuration set and SNS delivery events; EventBridge Scheduler every 15 minutes; log groups/alarms and an SNS alert topic.
* GitHub OIDC provider (or existing provider ARN) and deployment role restricted to this repository’s `main` branch. Separate task/execution roles. No administrator credentials in runtime services.

## Monthly estimate

Assume 730 running hours, low traffic, one copy of each service, no free-tier credits/discounts, no tax, and no paid domain purchase. AWS Price List API rates were queried for Mumbai; sanitized results are in [aws-preflight.json](aws-preflight.json).

| Component | Calculation / allowance | USD per month |
|---|---|---:|
| Fargate CPU | 1.25 × 730 × $0.04256 | 38.84 |
| Fargate memory | 2.5 × 730 × $0.004655 | 8.50 |
| RDS instance | 730 × $0.021 | 15.33 |
| RDS storage/backups | 20 GiB plus modest backup allowance | 3–6 |
| ALB | $0.0239/hour + 0.5–1 LCU at $0.008/LCU-hour | 20.37–23.29 |
| Public IPv4 | 3 tasks + 1 gateway Elastic IP, $0.005/address-hour | 14.60 |
| HTTPS gateway | t2.micro: 730 × $0.0124, plus 8 GiB gp3 | about 10 |
| S3/ECR/KMS/secrets/logs/queues | Low-volume allowance; workload dependent | 8–18 |
| **Baseline estimate** | Rounded planning range | **$120–150** |

The table prices the live IP-gateway/private-ALB setup. Certificate issuance is free; renewal checks run every four hours. There is no CloudFront distribution or paid domain. The gateway is a single point of failure in this development environment.

The chosen development alert budget is **$150/month**, before meaningful interview volume. It is an alert threshold, **not a spending cap**. The `Project` cost-allocation tag is active and the alert email subscription is confirmed. RDS burst CPU credits, extra ALB IPs/LCUs, storage, data transfer, retries, and deployment overlap can raise the bill.

## Approximate 30-minute interview

Conservative example: 30 transcribed minutes; 3,000 Polly neural characters; 60 sampled frames (one per 30 seconds); 40,000 input/8,000 output model tokens; 120 MB of video retained one month; five emails.

| Meter | Assumption | Approximate USD |
|---|---|---:|
| Transcribe | $0.024/minute planning rate × 30 | 0.72 |
| Polly neural | $16/million characters × 3,000 | 0.048 |
| Rekognition DetectFaces | $0.001/frame × 60 | 0.060 |
| Groq pilot inference | No paid plan enabled; free account quotas constrain usage | 0 within free limits |
| S3 requests/storage, KMS, email | Allowance, including incremental clips | 0.01–0.04 |
| **Variable total** | Excludes baseline, downloads, tax, OCR | **about $0.85–0.90** |

For 100 such interviews/month, plan approximately **$205–240/month total**, so increase the alert budget explicitly or reduce volume. The application defaults to 3,000 allocated interview minutes per organization per UTC calendar month; this is not an account-wide currency cap. Half-duplex operation may reduce actual transcribed minutes, but do not budget on that saving until measured. A ten-page scanned PDF adds bounded Textract cost; normal PDF/DOCX parsing is local.

Fargate, RDS, ALB and Polly values above were checked against the regional pricing API. Transcribe/image rates are planning assumptions from AWS published pricing. Groq inference is the authorized exception to AWS-only processing; a paid provider plan would add its own charges. Bedrock is optional and account-blocked.

Sources: [Fargate pricing](https://aws.amazon.com/fargate/pricing/), [RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/), [ALB pricing](https://aws.amazon.com/elasticloadbalancing/pricing/), [IPv4 pricing](https://aws.amazon.com/vpc/pricing/), [Transcribe pricing](https://aws.amazon.com/transcribe/pricing/), [Polly pricing](https://aws.amazon.com/polly/pricing/), [Rekognition pricing](https://aws.amazon.com/rekognition/pricing/), [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).

## Production upgrades

Price separately: multi-AZ RDS, at least two API/web tasks, separate worker scaling, connection pooling, stronger edge rate limiting, private endpoints or NAT, dedicated migration/database users, backup restoration drills, regional residency validation, and live load testing. Ten local synthetic sessions do not establish Fargate production capacity.
