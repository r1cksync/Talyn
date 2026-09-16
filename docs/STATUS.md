# Implementation and verification status

Updated 16 September 2026. **Development URL: https://13.204.206.74**. The AWS environment is deployed; the complete generated-media cloud interview acceptance passed. This is a development pilot with the limits below.

The complete workflow acceptance used commit `daa5d55`; the current deployed image is `b6982ef`, including complete candidate feedback and correct selection of new invitations over an existing candidate session. Infrastructure commit `882b85e` adds scoped SES permissions for configured sandbox recipients; that permission-only deployment reused the same images. Public feedback/access browser checks passed on this image. Evidence is recorded in [acceptance](acceptance.md). Implementation, fixture testing and real provider verification are distinguished here.

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

## Checks and operational state

- The complete browser suite passed: five tests covering the end-to-end interview, responsive landing, feedback empty states and transcripts, invitation precedence, and explicit resume selection. Three targeted checks also passed against the deployed frontend using fixture API responses. Three audio resampling tests passed. Next.js production build and TypeScript checks passed.
- GitHub CI runs backend suites on both SQLite and PostgreSQL, migrations, browser tests and three CDK infrastructure suites. It synthesizes the IP, optional custom-domain and optional CloudFront paths. Final CI: 21 passed/one skipped on SQLite, 22 passed on PostgreSQL, five browser tests, three audio tests and three infrastructure suites. Source CI `35103582740` passed; application deployment `35102246329` passed.
- Ten simultaneous local PostgreSQL synthetic interviews completed; the eleventh was rejected with 429 and capacity returned to zero. This is not a live AWS load test. The selected free Groq pilot allows two concurrent interviews per organization.
- All eight real cloud acceptance stages passed on task `2f621f839c9f4c90bede7e48168f393c` with exit 0. Media was generated and streamed over the public interface; real camera/device behavior was tested separately in Chromium using synthetic fixtures.
- The SES sender is verified; its sandbox remains enabled. The alert SNS email subscription is confirmed. The Project billing tag is active. A $150 monthly budget provides alerts, not a spending cap. The selected development baseline is approximately $120–150/month before interview usage.
- Trusted IP HTTPS and a certificate renewal dry run passed. Renewal checks run every four hours. No domain was purchased.

## Remaining external and production prerequisites

Bedrock account authorization and CloudFront account verification remain blocked; both have working authorized alternatives (Groq and the IP gateway). No additional administrator key is needed. See [AWS blockers](aws-blockers.md).

A fresh ten-minute practice interview was prepared in the same demo recruiter workspace with a fictional resume and reviewed three-competency plan. Its invitation was delivered to the owner's verified college inbox; the session was left unstarted. Further sandbox recipients require verification and the configured allowlist/identity permissions. Unverified recipients require SES production access and deliberate email configuration. Signup/email verification in a real inbox, scanned-PDF Textract, live bounce/complaint events, Safari/Firefox, ten concurrent live interviews, and a database restore drill remain unverified. They are not represented as completed tests. See [limitations](limitations.md).

No Kaggle dataset or training was needed. Credentials, task.txt, the private reference checkout and generated test artifacts are excluded from Git.
