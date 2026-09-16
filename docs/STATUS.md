# Implementation checklist

Legend: implemented = code exists; tested = named checks passed; deployed = running AWS resource verified. These are separate claims.

| Milestone | Implemented | Tested | Deployed / blocked |
|---|---|---|---|
| Foundation, tenancy, auth, database | Implemented | SQLite + PostgreSQL authorization/migration tests | Cognito cloud acceptance pending |
| Jobs, ingestion, preparation | Implemented | Synthetic PDF/DOCX policy and preparation tests | Bedrock blocked; user selected Groq, integration underway |
| Invitations and access | Implemented | OTP, expiry, replay, CSRF, revocation and recipient isolation | SES verification requested |
| Live audio interview | Implemented | PCM at 16/44.1/48 kHz; actual WS route finalization/reconnect with provider fixture; real Polly/Transcribe smoke | Full deployed interview pending |
| Video and observations | Implemented | Browser recording, checksum, missing manifest sequence, decoded playback | Rekognition cloud acceptance pending |
| Reports and notifications | Implemented | Evidence validation, audience isolation, annotations, outbox replay, retention | Live model/email acceptance pending |
| Infrastructure and E2E | Implemented | Two CDK assertion suites + synth, Docker builds, complete browser journey | Deployment pending provider integration |

Latest checks: 15 backend tests passed on PostgreSQL (19.92 seconds); earlier SQLite suite plus new websocket success/reconnect test passed. Three audio-resampling tests passed. Browser E2E passed in 30.4 seconds including 390px responsive overflow check. Both containers built and the PostgreSQL-backed Compose app answers `http://localhost:3000/api/health`.

Ten simultaneous local PostgreSQL synthetic workflows completed; the eleventh start was rejected with 429 and capacity returned to zero. Latest recorded metrics are in the ignored `.local/concurrency-result.json`. This is not a live cloud load test.

AWS resources created so far: one SES sender email identity, with verification requested. No ECS/RDS/S3/CDK infrastructure yet. Polly/Transcribe smoke calls incurred small metered usage. No Kaggle data/training was used. User confirmed no domain; infrastructure supports a generated CloudFront HTTPS address with a private ALB origin.
