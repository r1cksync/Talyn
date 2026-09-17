# Implementation and verification status

Updated 17 September 2026. **AWS deployment retired at the owner's request.** The former development IP is no longer a Talyn endpoint. The source and local synthetic demo remain available. The evidence below describes checks completed before teardown; see the [teardown record](teardown.md) for the final AWS state and preserved S3 data.

The last deployed image was `2d49b3d`, including the preparation request-size and call-allowance fix, candidate feedback, invitation selection, audio/database contention fixes, and recoverable recording uploads. The earlier public feedback/access/recovery checks ran on `231417c`. Evidence is recorded in [acceptance](acceptance.md). Implementation, fixture testing and historical real-provider verification are distinguished here.

| Milestone | Implemented and tested | Live AWS verification |
|---|---|---|
| Foundation, tenancy, auth, database | Tenant/role/session/CSRF tests on SQLite and PostgreSQL; migrations and concurrent startup | Cognito sign-in, organization creation, private RDS TLS and checkpoint storage passed |
| Jobs, ingestion, preparation | PDF/DOCX parsing, prompt boundaries, approved/versioned rubrics | Regional signed S3 upload with SHA-256, SQS extraction, real Groq preparation passed |
| Invitations and access | Expiry, replay, OTP, revocation and consent policy tests | SES simulator invitation/OTP, scoped candidate session and consent passed |
| Live audio interview | PCM resampling, stream finalization/reconnect, bounded follow-ups | Public WSS PCM streaming through Transcribe, Polly audio via signed S3 URL, multi-turn interview passed |
| Video and observations | Browser clips, decoded playback, missing-sequence recovery | Signed clip upload, final manifest and completed Rekognition frame job passed |
| Reports and notifications | Evidence quote validation, private annotations and audience isolation | Real Groq reports, separate candidate feedback, SES manager/candidate notifications passed |
| Infrastructure and UI | CDK assertions/synthesis, Docker, complete synthetic browser journey | Three Fargate services, private ALB and IP TLS gateway deployed; trusted HTTPS verified |
| Nightshift reference design | Landing and shared manager/candidate theme; self-hosted fonts; 1440px/390px checks | Deployed; public desktop/mobile navigation, workspace and browser S3 upload passed |

## Historical checks before teardown

- The complete browser suite passed: seven tests covering the end-to-end interview, responsive landing, feedback empty states and transcripts, invitation precedence, explicit resume selection, paused-upload recovery and completed-interview recovery without camera access. Five targeted checks also passed against the deployed frontend using fixture API responses. Three audio resampling tests passed. Next.js production build and TypeScript checks passed.
- GitHub CI runs backend suites on both SQLite and PostgreSQL, migrations, browser tests and three CDK infrastructure suites. It synthesizes the IP, optional custom-domain and optional CloudFront paths. Final CI: 23 passed/four PostgreSQL-only skips on SQLite, 27 passed on PostgreSQL, seven browser tests, three audio tests and three infrastructure suites. Source CI `35106972865` passed; application deployment `35107365477` passed. All three ECS services are healthy on image `231417c`.
- Ten simultaneous local PostgreSQL synthetic interviews completed; the eleventh was rejected with 429 and capacity returned to zero. This is not a live AWS load test. The selected free Groq pilot allows two concurrent interviews per organization.
- All nine real cloud acceptance stages passed on task `baa53e023ff5404db51f1178ce3c8d92` with exit 0. The first audio stream ran for at least 65 seconds while the runner repeatedly polled the session/health endpoints and uploaded recording clips and frames; recording verification and reports completed. Media was generated and streamed over the public interface; real camera/device behavior was tested separately in Chromium using synthetic fixtures.
- The SES sender is verified; its sandbox remains enabled. The alert SNS email subscription is confirmed. The Project billing tag is active. A $150 monthly budget provides alerts, not a spending cap. The selected development baseline is approximately $120–150/month before interview usage.
- Trusted IP HTTPS and a certificate renewal dry run passed. Renewal checks run every four hours. No domain was purchased.

## Remaining external and production prerequisites

Bedrock account authorization and CloudFront account verification remain blocked; both have working authorized alternatives (Groq and the IP gateway). No additional administrator key is needed. See [AWS blockers](aws-blockers.md).

The interrupted practice attempt and its five verified clips were preserved. After the recording fix passed live acceptance, a separate fresh ten-minute practice interview was prepared in the same demo recruiter workspace using the fictional resume and reviewed three-competency plan. Its replacement invitation was delivered to the owner's verified college Inbox at 14:27 UTC; the new application remains invited and unstarted. Browser-only pending clips still require recovery from the original browser profile. Further sandbox recipients require verification and the configured allowlist/identity permissions. Unverified recipients require SES production access and deliberate email configuration. Signup/email verification in a real inbox, scanned-PDF Textract, live bounce/complaint events, Safari/Firefox, ten concurrent live interviews, and a database restore drill remain unverified. They are not represented as completed tests. See [limitations](limitations.md).

No Kaggle dataset or training was needed. Credentials, task.txt, the private reference checkout and generated test artifacts are excluded from Git.
