# Talyn

An AWS-hosted, multi-tenant AI interview workspace. Managers approve a consistent rubric, candidates complete a consent-based interview, and reports link assessments to transcript evidence. Hiring decisions remain with people.

The synthetic application runs locally end to end. The user selected Groq inference because this AWS account blocks Bedrock. Real Groq extraction, plans, follow-ups and evidence-linked reporting passed a synthetic workflow. AWS deployment is in progress using a generated CloudFront HTTPS address. See [verification status](docs/STATUS.md). Synthetic results are always labeled.

Stack: Next.js / React / TypeScript, FastAPI / SQLAlchemy / Alembic, LangGraph, PostgreSQL and AWS CDK. Runtime integrates Cognito, S3, Transcribe Streaming, Polly, SES, SQS and Rekognition. LLM inference supports Bedrock and the explicitly authorized Groq alternative. Groq sends planning/answer text outside AWS, disclosed before consent.

## Run locally

With Docker Desktop running, from the repository root:

```sh
docker compose up --build -d
```

Open http://localhost:3000, choose **Open your workspace**, then **Enter synthetic demo**. Create an organization and role, add a synthetic candidate, upload a resume, prepare and approve the interview, then launch invitations. Notifications contains the simulated invitation link and verification code. Use a separate browser profile for candidate access. With consent, the candidate page records real camera/microphone clips; demo answers use the explicitly labeled synthetic input. Reports include evidence and independently playable clips. Demo mode sends no external email and makes no AWS AI calls.

The landing page and shared application theme adapt the user's private Nightshift reference: charcoal, acid yellow, large Anton headlines, Archivo body text and IBM Plex Mono labels. Fonts are self-hosted. Landing motion can be paused and respects reduced-motion preferences. The authenticated workspace is at `/workspace`; candidate invitations open `/interview`.

Generate sample documents and automated browser media with `cd backend`, `uv sync --frozen`, then `uv run python ../scripts/create_fixtures.py`. Files appear in `frontend/test-fixtures/`. For a lightweight Windows setup with Python 3.12, Node 22 and uv installed, run `powershell -File scripts/dev.ps1`; this uses SQLite instead of Docker PostgreSQL.

`docker compose stop` stops local containers and preserves demo data. Bindings are localhost only. The Compose password is exclusively a disposable local development credential. Do not expose the demo publicly.

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

See [architecture](docs/architecture.md), [deployment and rollback](docs/deployment.md), [operations](docs/operations.md), [costs](docs/costs.md), and [limitations](docs/limitations.md). No Kaggle data or training is required. `task.txt`, credentials, local data, generated fixtures and build artifacts are excluded by `.gitignore`.
