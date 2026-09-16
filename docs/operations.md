# Operating Talyn

| Symptom | Check and recovery |
|---|---|
| Preparation or report pending | Review application job status, worker logs and SQS/DLQ alarms. For Groq, check model availability, rate limits and Secrets Manager injection; for optional Bedrock, check account authorization/quota/model/role. Retry the failed job after correcting its cause; checkpoints reuse completed nodes. |
| Interview material exceeds the AI size limit | This is Talyn's development request-size guard, not evidence of exhausted Groq quota. Preparation sends each source text once and retains citation identifiers. Shorten oversized documents/job details or review the provider configuration. Input rejection stops automatic retries and consumes no model-call allowance. |
| AI request allowance exhausted | Check application usage and checkpoint state before retrying. Actual provider attempts remain charged, including failures. Correct a historical local-only rejection only when checkpoint timing and the unchanged oversized request prove it never reached the provider; retain the usage row at quantity zero and record the correction in the audit log. Do not reset the entire interview's usage. |
| Extraction fails | Check 10 MB PDF/DOCX limit, corruption, encryption and readable text. Replace the failed upload. Scanned PDFs need Textract; OCR defaults to a 10-page cap. |
| Invitation fails | Invitations expire in seven days and exchange once. Resume with application ID plus email OTP; revoked applications cannot resume. Never copy tokens/OTPs into support logs. |
| Audio disconnects | Check microphone/network and reconnect. Final captions persist; a new stream uses a new timeline offset. A stale connection lease expires in 30 seconds. Finite deployment drains cannot guarantee uninterrupted speech. |
| Polly playback fails | Read captions, then start listening. Transcription pauses during question playback. Headphones reduce acoustic echo in recordings. |
| Uploads delayed / recording paused | Keep the same browser profile and site data. Use **Retry uploads and resume** while the interview is active. Capture pauses at four pending clips; the queue continues draining. If the interview has ended, refresh and use **Retry saved uploads**. Saved clips can be uploaded for 24 hours after completion, without reopening the microphone/camera. Review missing sequences and timing gaps; an open unsaved clip cannot be recovered after browser failure. |
| Camera unavailable | Candidate requests an accommodation; owner/recruiter can waive recording. Camera observations never change competency scores. |
| Email missing | Check SES verification, sandbox, recipient allowlist, bounce/complaint suppression, SNS subscription and event queue. Demo notifications are simulated. |
| Login fails | Use a verified manager email. Password policy: 12 characters, upper/lowercase, digit and symbol. Check Cognito pool/client/region. Reauthenticate after a stale session expires. |
| Start returns 429 | Organization concurrency or monthly minutes exhausted. Starting reserves full duration; finishing releases unused minutes. Usage resets on the first start in each UTC month. |
| HTTPS fails | Check the gateway through SSM, nginx health, certificate lifetime and `talyn-tls.timer`. Port 80 must remain reachable for ACME renewal. See the certificate checks below. |
| Signed upload fails | Verify the URL hostname includes the bucket region. Legacy global S3 endpoints can redirect new buckets, breaking signatures/CORS. Check size, SHA-256 checksum and five-minute URL expiry. |
| Deployment health fails | Check migration logs, database TLS/network, secret/KMS grants, image SHA and ALB targets. Public task subnets require AWS endpoint/image egress. |

Outbox jobs commit with product changes. Worker leases/idempotency prevent ordinary replay duplicates. A crash after SES accepts email but before the delivery ID commits can resend it; this is not exactly-once delivery. SQS carries identifiers, not transcripts or tokens. Email bodies are encrypted in the database.

Application retention defaults to 30 days, including inactive applications; completion refreshes the deadline. Maintenance runs every 15 minutes to expire sessions, queue reminders and delete expired applications. Deletion covers all object versions, documents, transcript/report/evaluation records, observations, invitations, scoped sessions, checkpoint threads and related jobs. Audit metadata expires after 90 days; delivery payloads after 30 days. Backup expiration is separate; see deployment instructions.

Monitor API/worker/web CPU, ALB errors, database storage and dead letters. Confirm a monitored SNS subscriber. Ordinary logs omit tokens, request bodies, document text, transcripts and prompts. Usage tracks interview/transcription minutes, model calls/tokens, speech characters, storage, frames, OCR and emails.

Worker failures log the background job ID, kind, exception type and a fixed error code. Known local size/budget failures expose a safe recovery message in the manager UI and stop futile retries. Unknown exceptions retain a generic message; exception payloads must not be copied into user-facing errors or ordinary logs.

For PostgreSQL acceptance, create a separate `talyn_test` database and set `TALYN_TEST_DATABASE_URL=postgresql+psycopg://.../talyn_test`, then `uv run pytest -q`. Tests reset that database and refuse other names. CI creates a disposable PostgreSQL service.

## IP certificate checks

Use Systems Manager Session Manager or Run Command on the stack's `IpGatewayInstance`; SSH is disabled. These commands contain no credentials:

```sh
systemctl status nginx talyn-tls.timer
systemctl list-timers talyn-tls.timer
openssl x509 -enddate -noout -in /etc/letsencrypt/live/talyn-ip/cert.pem
journalctl -u talyn-tls.service --since '24 hours ago'
/opt/talyn-certbot/bin/certbot renew --dry-run --no-random-sleep-on-renew
```

The short-lived certificate is checked every four hours. The bootstrap/renewal service reloads nginx and publishes `Talyn/TLS / CertificateSecondsRemaining`; the alarm treats missing data and less than 24 hours remaining as failures. The staging renewal dry run passed on 16 September 2026. Confirm the SNS alert subscription in the selected inbox so these alarms reach a person.

The gateway is currently in the VPC's second public subnet (`ap-south-1b`): this account's first AZ had no T2 capacity. Gateway user-data changes replace the instance while preserving the Elastic IP, causing a brief interruption. Avoid deploying during interviews; even ordinary API rolling updates can interrupt a live utterance.
