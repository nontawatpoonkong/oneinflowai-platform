# Production Slip Verification

Sprint 9.3 integrates the official EasySlip API v2 for Customer Payment slip
verification. Customer Payment is money paid by an end customer directly to a
Workspace business; it is not OneInFlow SaaS Billing.

## Authoritative flow

Customer → JPEG/PNG evidence → local signature/size/ownership validation →
`EntitlementService` quota reservation → EasySlip API v2 → normalized provider
result → `PaymentVerificationService` deterministic checks → Payment status.

EasySlip does not directly set a Payment to `VERIFIED`. OneInFlow independently
requires the expected amount, currency, Workspace destination receiver,
ownership, evidence hash uniqueness, and transaction-reference uniqueness to
match. Provider duplicate signals also prevent verification.

## Provider contract and security

- The platform sends a validated image using the documented v2 multipart
  `image` input with `matchAccount`, `matchAmount`, and `checkDuplicate` enabled.
- The platform API key is server-side configuration only. It is never stored on
  a Workspace, returned by an API, or logged.
- Provider calls have a bounded timeout and no automatic retry.
- Provider failures are mapped to safe internal codes.
- Raw responses, QR payloads, OCR text, and full account details are not
  persisted or exposed. Only normalized verification fields are stored.

EasySlip processes payment evidence as a third party. DPA, retention, data
residency, subprocessor, incident-response, and PDPA review are required before
commercial production launch.

## Entitlement and usage

`payments.slip_verification` is evaluated from configured `PlanEntitlement`
data. No plan name or quota is hard-coded. An advisory transaction lock protects
the final quota unit; a usage reservation is committed before the external call
so the database lock is not held during network I/O. Local upload rejection and
entitlement denial do not consume usage. Once a production request is reserved
and attempted, timeout or provider failure retains that usage because the
provider may have accepted and billed the request.

## Limitations

- The development provider remains deterministic for local/test use.
- No provider request is automatically retried.
- LINE and Facebook remain text-first; Sprint 9.3 does not ingest slip images
  from those channels.
- Provider pricing is external and configurable, not OneInFlow pricing.

## Manual sandbox checklist

With sanitized test values, manually test a valid slip, wrong amount, wrong
receiver, duplicate image, duplicate transaction, malformed image,
timeout/provider error, exhausted quota, notification delivery, and a linked
Action. Do not execute real transfers automatically.
