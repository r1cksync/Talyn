# Development acceptance evidence

Date: 16 September 2026. Region: `ap-south-1`. URL: **https://13.204.206.74**. Repository: `r1cksync/Talyn`, branch `main`.

## Complete real-provider workflow

The committed operator runner `scripts/run_cloud_acceptance.py` launched one Fargate task using separately injected simulator-only Cognito credentials. Task `2f621f839c9f4c90bede7e48168f393c` exited **0**, running API image `daa5d554c0b66f3f8453dda480c9393ef4baf87d`.

All stages passed:

1. Trusted HTTPS, Cognito login and organization creation.
2. SHA-256 signed regional S3 document upload, SQS dispatch and document extraction.
3. Real Groq interview preparation, persisted PostgreSQL/LangGraph checkpoints and manager approval.
4. SES simulator invitation and OTP, scoped candidate access and versioned consent.
5. Public WebSocket PCM stream, real Transcribe final captions, Polly question playback and multi-turn interview completion.
6. Completed Rekognition job for a generated frame (no claim of face/person identification).
7. Recording manifest finalization, real Groq reports, evidence validation and isolation of manager-only notes from candidate feedback.
8. Separate candidate and manager report notifications accepted by SES.

The acceptance runner initially expires its synthetic application after one day. At the owner's request for a populated test login, this completed sample was retained until 16 October 2026 and made available in Talyn Demo Workspace through a separate recruiter account; credentials are kept outside Git. Its corresponding synthetic candidate now uses the owner's verified inbox for the normal resume/OTP flow, so the owner can open candidate feedback. No candidate password or authentication bypass was introduced. The runner prints stage names/identifiers, never passwords, signed URLs, invitation tokens or transcripts. It retrieves simulator-only OTPs from its own organization's encrypted outbox. This proves provider acceptance and the application's pipeline; it does not prove inbox delivery to a real candidate.

## Browser and infrastructure checks

The local production Docker frontend and PostgreSQL API passed both browser tests in **22.8 seconds**. The workflow uses fixture camera/microphone capture and verifies document preparation, invitations, consent, independent recording playback, reports and mobile layout. The landing test covers desktop and mobile pointer navigation, reduced motion and expandable principles.

The IP certificate is trusted without disabling TLS validation. The Certbot renewal dry run passed; `talyn-tls.timer` is enabled for four-hour checks. API health returns AWS mode. The ALB and database are private; application ingress is restricted to the ALB, and only gateway ports 80/443 are public.

CI passed on `d702be5`: **21 backend tests plus one PostgreSQL-only skip on SQLite; 22 passed on PostgreSQL; two browser tests; three audio tests; three infrastructure suites**. Migrations, type checking, production builds and all three ingress syntheses passed. [CI run](https://github.com/r1cksync/Talyn/actions/runs/35095914918). The latest local PostgreSQL suite passed all 22 tests in 28.20 seconds.

Final deployed application image: `d702be584388e1abe99e234d81c656cb358a8e58`. [Deployment run](https://github.com/r1cksync/Talyn/actions/runs/35096267050).

The public-site Chromium check passed with normal certificate verification: desktop landing pointer navigation, Cognito browser login, secure HttpOnly SameSite cookies, real browser camera/microphone APIs using fixture devices, direct browser-to-S3 CORS/checksum upload and document completion, workspace rendering and 390px layout without horizontal page overflow. No uncaught page errors occurred. Desktop/mobile screenshots were visually reviewed.

Three known SES setup notifications from the earlier dead-letter queue were returned to the email-event queue after the fix; the worker acknowledged them. Job, email-event and dead-letter queues were all empty on the final check. Other messages were not modified.

## Defects found and corrected during acceptance

- FastAPI database dependencies now commit before HTTP success is sent, preventing a follow-up request from missing a just-created record.
- Concurrent API/worker initialization uses a bounded, autocommit advisory-lock loop to avoid blocking PostgreSQL concurrent index creation with an idle snapshot.
- Signed S3 URLs explicitly use the Mumbai endpoint, avoiding newly created bucket redirects.
- Oversized landing typography is clipped within its decorative element; clipping the entire page caused Chromium pointer hit testing to drift after scrolling.
- SES's plain-text SNS setup notification is acknowledged explicitly. Invalid delivery events remain errors, duplicate events are idempotent and late delivery events cannot undo bounce/complaint suppression.

## Limits

Generated media was used for the live protocol test. Scanned-PDF OCR, live bounce/complaint simulation, real-inbox signup, Safari/Firefox, backup restore and ten simultaneous live AWS interviews were not verified. Ten simultaneous deterministic workflows passed locally. Single tasks, a single gateway, single-AZ RDS and the free Groq quota are development constraints.

## Candidate feedback and fresh practice interview

On 16 September 2026, image `b6982ef` added candidate/role/date context, clear empty-state feedback, final answer transcripts and next-step guidance. New invitation links take precedence over an existing candidate cookie; explicit resume links cannot silently open another application. Verification retry controls do not submit the form. Five CI browser tests passed, and three targeted browser checks passed against the public frontend using mocked candidate responses (not a second live interview).

A separate ten-minute Backend Engineer practice job was created through the same demo recruiter account, with a fictional DOCX resume, successful S3 extraction and an approved plan covering technical reasoning, problem solving and collaboration. Questions explicitly treat the fictional projects as scenarios. The original completed sample was preserved.

The requested college recipient was verified with SES. The first send exposed a missing recipient-identity IAM permission in sandbox mode. Infrastructure commit `882b85e` adds only configured recipient identities while retaining the fixed sender condition and application allowlist; CDK diff showed one IAM policy change. After the permission-only deployment, the existing failed outbox job was retried. SES reported `delivered`, and the invitation was independently confirmed in the recipient's Inbox at 13:43 UTC. The application remained `invited`, with no interview started by the agent. Recipient details, resume and operator evidence remain in ignored local files.
