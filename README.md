# Talyn

An AWS-hosted, multi-tenant AI interview workspace. Managers approve a consistent rubric, candidates complete a consent-based interview, and reports link assessments to transcript evidence. Hiring decisions remain with people.

**Under active implementation.** See [implementation status](docs/STATUS.md) for tested and deployment status. Synthetic demo results are always labeled.

Stack: Next.js / React / TypeScript, FastAPI / SQLAlchemy / Alembic, LangGraph, PostgreSQL, and AWS CDK. Runtime integrations use AWS Bedrock, Cognito, S3, Transcribe Streaming, Polly, SES, SQS, and Rekognition.

See [architecture](docs/architecture.md) and [deployment](docs/deployment.md). Never commit credentials. No Kaggle data or model training is required for this MVP.
