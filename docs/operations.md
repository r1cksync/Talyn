# Operating Talyn

| Symptom | Check and recovery |
|---|---|
| Preparation or report pending | Review application job status, worker logs and SQS/DLQ alarms. Check Bedrock authorization/quota/model/role. Retry the failed job after correcting its cause; checkpoints reuse completed nodes. |
| Extraction fails | Check 10 MB PDF/DOCX limit, corruption, encryption and readable text. Replace the failed upload. Scanned PDFs need Textract; OCR defaults to a 10-page cap. |
| Invitation fails | Invitations expire in seven days and exchange once. Resume with application ID plus email OTP; revoked applications cannot resume. Never copy tokens/OTPs into support logs. |
| Audio disconnects | Check microphone/network and reconnect. Final captions persist; a new stream uses a new timeline offset. A stale connection lease expires in 30 seconds. Finite deployment drains cannot guarantee uninterrupted speech. |
| Polly playback fails | Read captions, then start listening. Transcription pauses during question playback. Headphones reduce acoustic echo in recordings. |
| Media incomplete | Keep this browser profile and reconnect. Reload the completed interview to retry saved IndexedDB clips/manifest. Do not clear site data before recovery. Review missing sequences and timing gaps. |
| Camera unavailable | Candidate requests an accommodation; owner/recruiter can waive recording. Camera observations never change competency scores. |
| Email missing | Check SES verification, sandbox, recipient allowlist, bounce/complaint suppression, SNS subscription and event queue. Demo notifications are simulated. |
| Login fails | Use a verified manager email. Password policy: 12 characters, upper/lowercase, digit and symbol. Check Cognito pool/client/region. Reauthenticate after a stale session expires. |
| Start returns 429 | Organization concurrency or monthly minutes exhausted. Starting reserves full duration; finishing releases unused minutes. Usage resets on the first start in each UTC month. |
| Deployment health fails | Check migration logs, database TLS/network, secret/KMS grants, image SHA and ALB targets. Public task subnets require AWS endpoint/image egress. |

Outbox jobs commit with product changes. Worker leases/idempotency prevent ordinary replay duplicates. A crash after SES accepts email but before the delivery ID commits can resend it; this is not exactly-once delivery. SQS carries identifiers, not transcripts or tokens. Email bodies are encrypted in the database.

Application retention defaults to 30 days, including inactive applications; completion refreshes the deadline. Maintenance runs every 15 minutes to expire sessions, queue reminders and delete expired applications. Deletion covers all object versions, documents, transcript/report/evaluation records, observations, invitations, scoped sessions, checkpoint threads and related jobs. Audit metadata expires after 90 days; delivery payloads after 30 days. Backup expiration is separate; see deployment instructions.

Monitor API/worker/web CPU, ALB errors, database storage and dead letters. Confirm a monitored SNS subscriber. Ordinary logs omit tokens, request bodies, document text, transcripts and prompts. Usage tracks interview/transcription minutes, model calls/tokens, speech characters, storage, frames, OCR and emails.

For PostgreSQL acceptance, create a separate `talyn_test` database and set `TALYN_TEST_DATABASE_URL=postgresql+psycopg://.../talyn_test`, then `uv run pytest -q`. Tests reset that database and refuse other names. CI creates a disposable PostgreSQL service.
