# Implementation checklist

Legend: implemented = code exists; tested = named checks passed; deployed = running AWS resource verified. These are separate claims.

| Milestone | Implemented | Tested | Deployed / blocked |
|---|---|---|---|
| Foundation, tenancy, auth, database | Implemented | SQLite + PostgreSQL authorization/migration tests | Cognito cloud acceptance pending |
| Jobs, ingestion, preparation | Implemented | Synthetic PDF/DOCX tests; real Groq extraction and planning | Groq selected and configured in Secrets Manager |
| Invitations and access | Implemented | OTP, expiry, replay, CSRF, revocation and recipient isolation | SES sender verified; sandbox remains enabled |
| Live audio interview | Implemented | PCM at 16/44.1/48 kHz; actual WS route finalization/reconnect with provider fixture; real Polly/Transcribe smoke | Full deployed interview pending |
| Video and observations | Implemented | Browser recording, checksum, missing manifest sequence, decoded playback | Rekognition cloud acceptance pending |
| Reports and notifications | Implemented | Evidence validation, audience isolation, annotations, outbox replay, retention | Live model/email acceptance pending |
| Infrastructure and E2E | Implemented | Two CDK assertion suites + synth, Docker builds, complete browser journey | Foundation deployed; runtime provisioning |
| Nightshift-inspired interface | Implemented | Desktop/mobile screenshots, reduced motion, navigation, complete interview journey | Committed and pushed; deployment pending |

Latest checks: 17 backend tests passed on PostgreSQL (21.06 seconds) and SQLite (6.09 seconds). Three audio-resampling tests passed. Both browser tests passed in 25.6 seconds, covering the new landing page and full interview workflow, including 390px overflow checks. TypeScript and the Next.js production build passed. Docker/PostgreSQL end-to-end tests passed before the visual redesign; the new frontend was then exercised against the same PostgreSQL-backed API.

Ten simultaneous local PostgreSQL synthetic workflows completed; the eleventh start was rejected with 429 and capacity returned to zero. Latest recorded metrics are in the ignored `.local/concurrency-result.json`. This is not a live cloud load test.

AWS foundation is deployed: CDK bootstrap, VPC, private encrypted RDS PostgreSQL, encrypted S3, queues, KMS/secrets, Cognito, ECR repositories, ECS cluster, budget/alerts and GitHub OIDC. Runtime provisioning is underway. The SES identity is verified. The alert SNS subscription still awaits the user's inbox confirmation. The Project billing tag has been activated. Polly/Transcribe smoke calls incurred small metered usage. No Kaggle data/training was used. No domain purchase is required; the runtime uses a generated CloudFront HTTPS address with a private ALB origin.
