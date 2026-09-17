# Development acceptance evidence

Historical evidence: the AWS environment was retired on 17 September 2026. The former IP below is no longer a Talyn endpoint; see [teardown](teardown.md).

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


## Recording pause and API contention regression

The interrupted practice interview exposed a shared API event-loop stall: synchronous SQLAlchemy row-lock waits in the async audio WebSocket handler prevented the event loop from completing concurrent HTTP transactions. The async frame route also performed blocking S3 work. ECS marked the API unhealthy and replaced the task. Five clips (about 50 seconds) had already uploaded and verified; they were preserved.

Commit `f8d0ebb` moves each WebSocket database unit of work into a worker thread and makes frame processing a synchronous FastAPI handler, with the request body parsed before database work. A controlled regression against the previous source failed all four contention checks: audio start, heartbeat and stop under a PostgreSQL row lock, and slow frame storage alongside a health request. All four pass with the fix. The recording recovery window is now 24 hours, with completed-interview timestamp validation retained.

Commit `231417c` adds bounded recording-request/upload timeouts, queues the last saved clip even when backlog pauses capture, retries transient upload failures without a permanent recorder error, resumes the existing recorder, and provides explicit active/completed upload retry controls. The four-clip capture limit remains. Two browser regressions cover draining all saved clips and resuming capture after a stalled request, plus recovery after completion without requesting camera access.

[Source CI](https://github.com/r1cksync/Talyn/actions/runs/35106972865) passed: 23 backend tests and four PostgreSQL-only skips on SQLite; 27 passed on PostgreSQL; seven browser tests; three audio tests; three infrastructure suites; migrations, type checking, production builds and all ingress syntheses. Five targeted browser checks also passed against the local Next.js development server. Browser tests use isolated synthetic fixtures; the user's personal Chrome profile was not accessible through the tools in this session.

[Deployment](https://github.com/r1cksync/Talyn/actions/runs/35107365477) completed successfully. All three ECS services are healthy on image `231417cf6cba4c901b0e69c6705029290fa310e6`; trusted public HTTPS health returns AWS mode. Five targeted browser checks passed against the deployed frontend with fixture API responses, including both upload recovery cases.

The expanded live acceptance runner used this image in task `baa53e023ff5404db51f1178ce3c8d92` and exited **0**. All nine stages passed, including a first audio stream lasting at least 65 seconds, at least 15 concurrent session/health probes, repeated signed recording uploads (at least five clips in total), and frame sampling while audio was active. Real Transcribe, Polly, Rekognition, Groq, S3/SQS and SES simulator report notifications completed; the final recording manifest verified. This was a separate generated-media application, not the owner's replacement interview.

After live acceptance passed, the owner-authorized replacement practice invitation was sent once using an idempotent campaign. SES reported `delivered`; the new email was independently confirmed in the verified college Inbox at **14:27:35 UTC / 19:57:35 IST** on 16 September 2026. The new application remained `invited`, with no interview started by the agent. It uses the same recruiter workspace, fictional resume and reviewed three-competency scenario plan. The interrupted application and its five verified clips remain intact. Any additional pending clips must be recovered from the original browser/profile using the deployed retry controls; they were not claimed as recovered.

## Reviewer email access

On 16 September 2026, an additional reviewer received the owner-requested SES identity verification email in `ap-south-1`; a subsequent AWS lookup reported `Success`. The account remains in the SES sandbox. The deployment variable `TALYN_ADDITIONAL_EMAIL_RECIPIENTS` now includes this recipient while preserving the existing demo recipients. The recipient address remains outside Git.

The configuration update adds the recipient to the API and worker email allowlists and to the worker's scoped `ses:SendEmail` identity resources, retaining the fixed sender condition and `TALYN_LIVE_EMAIL=false`. It reuses application image `231417cf6cba4c901b0e69c6705029290fa310e6`. The reviewer can create their own job and invitation through the demo recruiter account; no reviewer job, candidate record or interview invitation was created during this setup.

Post-deployment checks at 15:24 UTC confirmed CloudFormation `UPDATE_COMPLETE`, all three ECS services healthy on the existing image, both updated recipient allowlists, the scoped sender-constrained IAM permission, SES verification `Success`, and trusted public HTTPS health in AWS mode.

## Preparation request size and call allowance regression

A failed preparation on 16 September 2026 retained a valid extraction checkpoint but repeatedly rejected question generation locally. The model payload included the extracted resume both as full text and as cited source text, producing a 27,952-character serialized request against Talyn's 24,000-character development guard. Call reservations happened before this local check, eventually exhausting the application's 12-call allowance. These rejected generation requests did not reach Groq; the final generic `ValueError` concealed the cause.

Commit `2d49b3d` sends cited source text once, including when resuming older checkpoints, and validates Groq input before reserving a model call. The affected request becomes 18,661 characters without truncating its sources. Known input-size and call-budget failures now show fixed recovery messages, log a safe error code with the background job ID, and stop futile automatic retries. Actual provider failures remain charged. Usage enforcement sums metered quantities, allowing an audited correction to retain a rejected local reservation at zero quantity.

[Source CI](https://github.com/r1cksync/Talyn/actions/runs/35118342107) passed: 26 backend tests plus four PostgreSQL-only skips on SQLite, 30 passed on PostgreSQL, seven browser tests, audio tests, infrastructure assertions, production builds and migration checks. New regressions exercise recovery from a legacy checkpoint with a long resume and corrected usage, complete source preservation, local rejection without provider calls or retries, and continued charging for real provider attempts.

A scoped operator task verified that the saved generation request exceeded the guard before HTTP submission and that its compact equivalent passed. It corrected only the 11 unpaired call reservations after the generation checkpoint, retaining the successful extraction call and recording affected usage IDs in the audit log. The application, resume and checkpoint were preserved; recipient details and operator artifacts remain outside Git.

[Deployment](https://github.com/r1cksync/Talyn/actions/runs/35118696471) succeeded. At 16:04 UTC all three services were healthy on image `2d49b3d4ed831f3c97cf5c2eb4c3a9164ab8cfb0`, public HTTPS health passed, and the reviewer recipient configuration and SES verification remained intact. Retrying the existing background job through the normal manager API succeeded on its first attempt: application `prepared`, job `done`, two questions available, plan still unapproved. The returned plan contains shared questions; this provider response yielded no personalized additions. No invitation was sent during recovery.
