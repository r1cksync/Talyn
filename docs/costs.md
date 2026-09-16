# Development resource plan and cost assumptions

Plan prepared before provisioning and updated 16 September 2026. Region `ap-south-1` (Mumbai). Project tag `Project=talyn`. Foundation infrastructure is now provisioned and incurs charges. Runtime/acceptance status is in [STATUS](STATUS.md). Synthetic Polly/Transcribe requests were made; AWS determines their metered charge.

## Concrete resource plan

* One VPC across two availability zones, two public application subnets, two isolated database subnets, an S3 gateway endpoint. **Zero NAT gateways.**
* Three on-demand Linux/x86 Fargate tasks: API 0.5 vCPU/1 GiB; worker 0.5 vCPU/1 GiB; web 0.25 vCPU/0.5 GiB. 1.25 vCPU and 2.5 GiB total. Rolling deployments temporarily overlap tasks.
* Default after the user's no-domain clarification: a CloudFront-generated HTTPS address and private ALB VPC origin, with uncached API/WebSocket routing. The optional custom-domain path uses an internet-facing HTTPS ALB with an existing ACM certificate. Tasks accept inbound application traffic only from the ALB.
* One private, encrypted, single-AZ RDS PostgreSQL 16 `db.t4g.micro`, 20 GiB gp3 (30 GiB maximum autoscaling), seven-day automatic backups and deletion protection.
* One private versioned KMS-encrypted S3 media bucket; short-lived scoped upload/download URLs. One KMS key, two Secrets Manager secrets (generated database and session credentials).
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
| Public IPv4 | 3 tasks + at least 2 ALB addresses, $0.005/address-hour | 18.25+ |
| S3/ECR/KMS/secrets/logs/queues | Low-volume allowance; workload dependent | 8–18 |
| **Baseline estimate** | Rounded planning range | **$115–135** |

The table prices the optional public-ALB variant. Default CloudFront/private-ALB hosting removes approximately $7.30/month for two public ALB IPv4 addresses, then adds metered CloudFront requests/data transfer. Allow $0–5/month for a light development test (an allowance, not a fixed quote), producing a rounded **$110–135/month** baseline. No paid CloudFront subscription or domain purchase is required. Refresh [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/) for actual traffic; no free credits are assumed as a guarantee.

The chosen development alert budget is **$150/month**, before meaningful interview volume. It is an alert threshold, **not a spending cap**. Activate the `Project` cost-allocation tag and subscribe/confirm an alert recipient. A topic without a confirmed subscription will not send human email alerts. RDS burst CPU credits, extra ALB IPs/LCUs, storage, data transfer, retries, and deployment overlap can raise the bill.

## Approximate 30-minute interview

Conservative example: 30 transcribed minutes; 3,000 Polly neural characters; 60 sampled frames (one per 30 seconds); 40,000 input/8,000 output model tokens; 120 MB of video retained one month; five emails.

| Meter | Assumption | Approximate USD |
|---|---|---:|
| Transcribe | $0.024/minute planning rate × 30 | 0.72 |
| Polly neural | $16/million characters × 3,000 | 0.048 |
| Rekognition DetectFaces | $0.001/frame × 60 | 0.060 |
| Nova Lite | $0.06/million input + $0.24/million output planning rates | 0.0043 |
| S3 requests/storage, KMS, email | Allowance, including incremental clips | 0.01–0.04 |
| **Variable total** | Excludes baseline, downloads, tax, OCR | **about $0.85–0.90** |

For 100 such interviews/month, plan approximately **$200–225/month total**, so increase the alert budget explicitly or reduce volume. The application defaults to 3,000 allocated interview minutes per organization per UTC calendar month; this is not an account-wide currency cap. Half-duplex operation may reduce actual transcribed minutes, but do not budget on that saving until measured. A ten-page scanned PDF adds bounded Textract cost; normal PDF/DOCX parsing is local.

Fargate, RDS, ALB and Polly values above were checked against the regional pricing API. Transcribe/Nova/image rates are explicit planning assumptions from AWS published pricing and must be refreshed for the selected inference profile before live deployment. Inference may route within APAC; model pricing and permitted regions are verified during preflight.

Sources: [Fargate pricing](https://aws.amazon.com/fargate/pricing/), [RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/), [ALB pricing](https://aws.amazon.com/elasticloadbalancing/pricing/), [IPv4 pricing](https://aws.amazon.com/vpc/pricing/), [Transcribe pricing](https://aws.amazon.com/transcribe/pricing/), [Polly pricing](https://aws.amazon.com/polly/pricing/), [Rekognition pricing](https://aws.amazon.com/rekognition/pricing/), [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).

## Production upgrades

Price separately: multi-AZ RDS, at least two API/web tasks, separate worker scaling, connection pooling, stronger edge rate limiting, private endpoints or NAT, dedicated migration/database users, backup restoration drills, regional residency validation, and live load testing. Ten local synthetic sessions do not establish Fargate production capacity.
