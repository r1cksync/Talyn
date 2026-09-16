# Talyn

An AWS-hosted, multi-tenant AI interview workspace. Managers approve a consistent rubric, candidates complete a consent-based interview, and reports link assessments to transcript evidence. Hiring decisions remain with people.

**Live development site: https://13.204.206.74**. Choose **Open your workspace** to sign in or create an account. The complete real-provider cloud interview test passed using synthetic data and SES simulator recipients. [Verification evidence](docs/acceptance.md) separates live checks from local fixtures and production prerequisites.

The user selected Groq because this AWS account blocks Bedrock. Groq inference is configured server-side in Secrets Manager; HTTPS uses a static IP and trusted certificate because no domain is available and CloudFront is account-blocked. The local synthetic demo runs separately, with clearly labeled fixture results.

Stack: Next.js / React / TypeScript, FastAPI / SQLAlchemy / Alembic, LangGraph, PostgreSQL and AWS CDK. Runtime integrates Cognito, S3, Transcribe Streaming, Polly, SES, SQS and Rekognition. LLM inference supports Bedrock and the explicitly authorized Groq alternative. Groq sends planning/answer text outside AWS, disclosed before consent.

## Architecture

The diagrams cover the deployed application and its deployment, security and operations services. Regional resources run in **ap-south-1 (Mumbai)**. Solid arrows show active flows or dependencies; dashed arrows show administration, provisioning or explicitly labelled optional paths. Resource coverage was checked against the live `TalynFoundation` and `CDKToolkit` CloudFormation stacks and the application service integrations.

### Interview and data flow

```mermaid
flowchart TB
    Browser["Manager and candidate browsers"]
    subgraph VPC["Amazon VPC - Mumbai; two AZs; security groups; Internet Gateway"]
        Gateway["Amazon EC2 + Elastic IP<br/>nginx HTTPS / WebSocket gateway"]
        ALB["Elastic Load Balancing<br/>Internal Application Load Balancer"]
        subgraph Compute["Amazon ECS on AWS Fargate - application subnets"]
            Web["Next.js web service"]
            API["FastAPI service<br/>Interview state and live audio"]
            Worker["Python worker<br/>LangGraph and background jobs"]
        end
        DB[("Amazon RDS PostgreSQL<br/>Isolated subnets; single AZ<br/>Application data and checkpoints")]
        Endpoint["S3 gateway VPC endpoint"]
    end
    Cognito["Amazon Cognito<br/>Manager authentication"]
    Speech["Amazon Transcribe Streaming - captions<br/>Amazon Polly - question speech"]
    S3[("Amazon S3<br/>Private versioned documents,<br/>recordings, frames and speech")]
    Groq["Groq API - external to AWS<br/>Selected LLM"]
    Bedrock["Amazon Bedrock - alternative LLM<br/>Inactive; account authorization blocked"]

    Browser -->|HTTPS and WSS| Gateway
    Gateway -->|VPC proxy| ALB
    ALB -->|Pages and assets| Web
    ALB -->|API and audio WebSocket| API
    API -->|Sign-in and registration| Cognito
    API <-->|Live audio and synthesis| Speech
    API --> DB
    DB <-->|Outbox, jobs and results| Worker
    API --> Endpoint
    Worker --> Endpoint
    Endpoint --> S3
    Browser <-->|Signed uploads and playback| S3
    API --> Groq
    Worker --> Groq
    API -.->|Optional provider| Bedrock
    Worker -.->|Optional provider| Bedrock

    classDef optional fill:#fff4d6,stroke:#9a6700,color:#24292f,stroke-dasharray:5 5
    classDef external fill:#f0eaff,stroke:#8250df,color:#24292f
    class Bedrock optional
    class Groq external
```

Candidate invitation/OTP sessions are managed by the API and database; Cognito handles manager accounts. Fargate tasks use public IPs for outbound access, with inbound application traffic restricted to the ALB security group. RDS is isolated and there is no NAT gateway.

### Background processing and notifications

```mermaid
flowchart LR
    Scheduler["Amazon EventBridge Scheduler<br/>Maintenance every 15 minutes"]
    Jobs["Amazon SQS<br/>Background job queue"]
    Worker["ECS Fargate worker<br/>Reads database outbox;<br/>dispatches and processes jobs"]
    Media["Amazon S3<br/>Documents and sampled frames"]
    Rekognition["Amazon Rekognition<br/>Neutral frame observations"]
    Textract["Amazon Textract<br/>Scanned-PDF OCR fallback<br/>Implemented; not live-verified"]
    SES["Amazon SES<br/>Invitations, OTPs and report emails"]
    Events["Amazon SNS<br/>Email delivery, bounce<br/>and complaint events"]
    EventQueue["Amazon SQS<br/>Email event queue"]
    DLQ["Amazon SQS<br/>Shared dead-letter queue"]
    Inbox["Manager and candidate inboxes"]

    Scheduler --> Jobs
    Jobs <-->|Consume / dispatch| Worker
    Media -->|Read evidence| Worker
    Worker -->|Sampled frames| Rekognition
    Worker -.->|Scanned documents only| Textract
    Worker -->|Send queued email| SES
    SES --> Inbox
    SES --> Events
    Events --> EventQueue
    EventQueue -->|Update delivery status| Worker
    Jobs -->|Exhausted retries| DLQ
    EventQueue -->|Exhausted retries| DLQ

    classDef optional fill:#fff4d6,stroke:#9a6700,color:#24292f,stroke-dasharray:5 5
    class Textract optional
```

The API writes durable jobs to the database outbox; the worker publishes them to SQS. Video observations remain separate from competency scoring. SES notifications and their delivery events use separate paths through SNS and SQS.

### Deployment, security and operations

```mermaid
flowchart TB
    GitHub["GitHub Actions<br/>AWS CDK and Docker builds"]
    Operator["Authorized operator"]
    AlertInbox["Operator alert inbox"]
    ACME["Let's Encrypt / Certbot<br/>Active IP TLS certificate renewal"]

    subgraph AWS["AWS deployment and operations"]
        Identity["AWS IAM + AWS STS<br/>GitHub OIDC and temporary deployment credentials"]
        CFN["AWS CloudFormation<br/>TalynFoundation and CDKToolkit stacks"]
        Lambda["AWS Lambda - CDK custom-resource helpers<br/>OIDC provider and default security-group restriction"]
        Assets["Amazon S3<br/>CDK bootstrap assets"]
        ECR["Amazon ECR<br/>API / worker and web images; CDK bootstrap repository"]
        SSM["AWS Systems Manager<br/>Session Manager / Run Command<br/>Parameter Store bootstrap version and AMI lookup"]
        Runtime["Amazon ECS on AWS Fargate<br/>Web, API and worker services"]
        Gateway["Amazon EC2 gateway + Elastic IP<br/>Encrypted Amazon EBS root volume"]
        Roles["AWS IAM<br/>Scoped task, execution, gateway and scheduler roles"]
        Secrets["AWS Secrets Manager<br/>Database, session and Groq credentials"]
        KMS["AWS KMS<br/>Data encryption keys"]
        Data["Amazon RDS, S3, SQS and email-events SNS<br/>Encrypted application data"]
        CloudWatch["Amazon CloudWatch<br/>Container logs, metrics and alarms<br/>CPU, ALB errors, DB storage, DLQ and TLS expiry"]
        Budgets["AWS Budgets<br/>Project-tagged monthly cost alerts"]
        Alerts["Amazon SNS<br/>Operational and budget alert emails"]

        subgraph Alternatives["Implemented ingress alternatives - not deployed"]
            CloudFront["Amazon CloudFront<br/>VPC origin to internal ALB<br/>Account verification blocked"]
            ACM["AWS Certificate Manager - ACM<br/>Existing-domain HTTPS ALB option<br/>No custom domain configured"]
        end
    end

    GitHub -->|OIDC federation| Identity
    Identity -->|Authorize CDK deployment| CFN
    GitHub -->|Push versioned images| ECR
    GitHub -->|Publish CDK assets| Assets
    Assets --> CFN
    CFN -.->|Custom resources| Lambda
    CFN -.->|Provision application stack| Runtime
    CFN -.->|Optional ingress selection| Alternatives
    ECR -->|Pull images| Runtime
    SSM -.->|Bootstrap and AMI parameters| CFN
    Operator -->|Administer gateway without SSH| SSM
    SSM -.-> Gateway
    Gateway <-->|Certificate issuance and renewal| ACME
    Roles -.->|Authorize service access| Runtime
    Secrets -->|Read or inject credentials| Runtime
    KMS -.->|Encrypt| Secrets
    KMS -.->|Encrypt| Data
    KMS -.->|Encrypt container logs| CloudWatch
    Runtime -->|Logs and metrics| CloudWatch
    Gateway -->|Certificate expiry metric| CloudWatch
    Data -->|Database storage and queue metrics| CloudWatch
    CloudWatch -->|Alarm notifications| Alerts
    Budgets -->|Cost thresholds| Alerts
    Alerts --> AlertInbox

    classDef optional fill:#fff4d6,stroke:#9a6700,color:#24292f,stroke-dasharray:5 5
    class CloudFront,ACM optional
```

Lambda functions here support CDK provisioning; interview processing runs in Fargate. Current HTTPS uses the EC2 gateway and Let's Encrypt. CloudFront and ACM are optional alternatives shown with their deployment status; Route 53 is not provisioned. Textract is implemented and permissioned but awaits a live scanned-PDF test. Bedrock remains inactive while Groq is selected. See [architecture decisions](docs/architecture.md), [verification evidence](docs/acceptance.md) and [account blockers](docs/aws-blockers.md).

## Run locally

With Docker Desktop running, from the repository root:

```sh
docker compose up --build -d
```

Open http://localhost:3000, choose **Open your workspace**, then **Enter synthetic demo**. Create an organization and role, add a synthetic candidate, upload a resume, prepare and approve the interview, then launch invitations. Notifications contains the simulated invitation link and verification code. Use a separate browser profile for candidate access. With consent, the candidate page records real camera/microphone clips; demo answers use the explicitly labeled synthetic input. Reports include evidence and independently playable clips. Demo mode sends no external email and makes no AWS AI calls.

The landing page and shared application theme adapt the user's private Nightshift reference: charcoal, acid yellow, large Anton headlines, Archivo body text and IBM Plex Mono labels. Fonts are self-hosted. Landing motion can be paused and respects reduced-motion preferences. The authenticated workspace is at `/workspace`; candidate invitations open `/interview`.

Generate sample documents and automated browser media with `cd backend`, `uv sync --frozen`, then `uv run python ../scripts/create_fixtures.py`. Files appear in `frontend/test-fixtures/`. For a lightweight Windows setup with Python 3.12, Node 22 and uv installed, run `powershell -File scripts/dev.ps1`; this uses SQLite instead of Docker PostgreSQL.

`docker compose stop` stops local containers and preserves demo data. Bindings are localhost only. The Compose password is exclusively a disposable local development credential. Do not expose the demo publicly.

## Hiring manager upload samples

The [demo upload kit](demo-upload-kit/START-HERE.txt) contains three fictional resumes in PDF and DOCX, a candidate CSV, an optional project brief, and job fields matching the current website. Upload either format of each resume, not both. The bulk CSV uses placeholder addresses for importing/preparing candidates; use a verified and allowed inbox for live invitation tests. A local `03-candidate-self-test.csv`, when generated, is excluded from Git.

The included documents are ready to upload. To regenerate them on Windows with Node.js and Microsoft Word installed:

```powershell
npm install --prefix .local/demo-kit-tools --save-exact --no-audit --no-fund docx@9.7.1
$env:NODE_PATH=(Resolve-Path '.local/demo-kit-tools/node_modules').Path
node scripts/create_demo_upload_kit.cjs --self-email your-verified-address@example.com
./scripts/export_demo_pdfs.ps1
```

Replace the example email with your verified inbox. Generation sends no email and creates no AWS jobs. All eight PDF/DOCX files were checked with Talyn's isolated document parser; DOCX schema checks and visual review of every exported PDF page passed. Candidate CSVs and job fields were checked against the application's input schemas.

## Checks

```sh
cd backend
uv sync --frozen
uv run ruff check app tests
uv run pytest -q
uv run alembic upgrade head
uv run alembic check
uv run python ../scripts/create_fixtures.py
cd ../frontend
npm ci
npx playwright install chromium
npm run typecheck
npm run test:audio
npm run build
npm run test:e2e
cd ../infra
npm ci
npm run build
npm test
```

CI repeats backend tests against a separate PostgreSQL database. Tests reset only a database named `talyn_test`; never provide a production database URL. Browser tests use fixture media and simulated recipients.

See [architecture](docs/architecture.md), [deployment and rollback](docs/deployment.md), [operations](docs/operations.md), [costs](docs/costs.md), and [limitations](docs/limitations.md). No Kaggle data or training is required. `task.txt`, credentials, local data, generated browser fixtures and build artifacts are excluded by `.gitignore`.
