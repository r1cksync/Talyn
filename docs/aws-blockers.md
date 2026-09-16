# Live AWS prerequisites and observed blockers

Checked on 16 September 2026 using the user-provided credentials. No credentials are committed or included here.

1. **Bedrock account/model authorization.** `GetFoundationModelAvailability` returned `authorizationStatus: NOT_AUTHORIZED` for Nova Lite, Nova Micro, and Nova 2 Lite, while agreement, entitlement, and region availability were `AVAILABLE`. Nova Lite APAC profile is `ACTIVE`. `Converse` returned `ValidationException: Operation not allowed` using both root and a narrowly scoped, temporary STS federated session. The account's Nova Lite cross-region RPM/TPM and daily token quotas are zero; RPM quota `L-89F8391A` is not self-adjustable. More administrator keys are not established as a remedy.
2. **CloudFront account verification.** Distribution creation returned HTTP 403: the account must be verified through AWS Support before adding CloudFront resources. Request ID `956730e5-3dce-42aa-87ed-30f5b88af101`. CloudFormation rolled back that runtime attempt. The user-approved IP fallback uses a small AWS nginx gateway and automatically renewed, trusted IP certificate; no domain purchase is required.
3. **SES sender verified.** The selected Gmail identity is verified in Mumbai (`SUCCESS`). Sandbox limits remain 200 messages/day and 1/second. Development uses the verified sender/recipient and simulator. Production access is required for arbitrary recipients; the allowlist stays enabled.
4. **Alert recipient selected.** The same user-controlled inbox will receive budget/operational alerts; confirm its SNS subscription after provisioning. Alerts are not a hard spending cap.

Polly neural speech and real Transcribe Streaming were successfully exercised with a generated synthetic phrase. Final transcript received: “This is a synthetic talent connection test.” That recognition difference is retained as evidence; it is not silently corrected.

The user confirmed Bedrock playground failure, explicitly selected Groq and supplied its key. The key is in AWS Secrets Manager. Real Groq inference passed extraction, personalized planning, two follow-up assessments and evidence-linked evaluation: five calls, 3,721 input and 1,194 output tokens using synthetic information. Bedrock itself remains blocked, but is no longer the selected provider.

## Suggested AWS Support request (draft, not sent)

Subject: Bedrock Nova account authorization returns NOT_AUTHORIZED / Operation not allowed

Please investigate Bedrock account/model eligibility in `ap-south-1`. On 16 September 2026, `Converse` for `apac.amazon.nova-lite-v1:0` returned `ValidationException: Operation not allowed`, including with root credentials and a scoped STS federated session. `GetFoundationModelAvailability` for `amazon.nova-lite-v1:0`, `amazon.nova-micro-v1:0`, and `amazon.nova-2-lite-v1:0` reports agreement/entitlement/region AVAILABLE but authorization NOT_AUTHORIZED. Nova Lite cross-region quota `L-89F8391A` is zero and not adjustable through Service Quotas. Please identify and resolve the account-level authorization or billing eligibility prerequisite and enable a modest development quota sufficient for 10 concurrent interview sessions.

Do not attach access keys to the support request. Attach sanitized preflight output and a new request ID from a failed invocation if AWS requests it.

[AWS model-access documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) describes current automatic access and authorization prerequisites. The observed error and zero quotas are account evidence; the exact restriction must be confirmed by AWS.
