# Channel integrations

Sprint 9.0 implements text-first WebChat, LINE OA, and Facebook Page Messenger
through a shared Channel Integration Layer. Instagram, Facebook Comments, Lead
Ads, broadcasts, media/slip ingestion, rich menus, Flex builders, and marketing
automation are outside this sprint.

## Shared flow

```text
authenticated webhook -> provider normalization -> trusted ChannelConnection
-> tenant-safe CustomerIdentity -> Customer/Conversation -> idempotent Message
-> shared RAG/Action Collection/Handoff core -> assistant Message
-> PENDING delivery -> provider adapter -> SENT or FAILED
```

LINE/Facebook business logic does not contain RAG, Action, Payment, or Handoff
rules. WebChat continues to use the same orchestration directly.

## Credential security

Set `CHANNEL_CREDENTIAL_ENCRYPTION_KEY` to a base64 encoding of exactly 32
random bytes in the server environment. Never commit or expose it. AES-256-GCM
uses a fresh 12-byte nonce and AAD containing workspace ID, connection ID, and
provider. Only ciphertext, nonce, and key version (`v1`) are stored.

Missing/malformed keys, wrong AAD/version, modified ciphertext, or authentication
failure stop credential operations. Unrelated backend startup remains available.
KMS/Vault and automated key rotation are not implemented yet.

## Webhook and identity security

- LINE requires a valid `X-Line-Signature` HMAC before JSON parsing/processing.
- Facebook GET validates the configured verification token; POST requires valid
  `X-Hub-Signature-256` HMAC.
- Connection IDs resolve trusted workspace/provider credentials. Payloads cannot
  select a workspace or provide access tokens.
- `(channel_connection_id, external_user_id)` isolates LINE IDs/PSIDs across
  workspaces and accounts.
- Facebook echo/self messages and unsupported/non-text events are ignored.
- Payload size and provider timeouts are bounded; official fixed API bases avoid
  client-controlled destinations.

## Idempotency, Action Collection, and delivery

Provider message IDs use `Message.external_message_id`, preserving the existing
conversation-scoped unique constraint and race-safe claim. Duplicate inbound
events do not rerun AI, Action Collection, notifications, or outbound sends.

Channel customers can confirm an `AWAITING_CONFIRMATION` Action Collection only
with an exact `confirm`, `confirm request`, `ยืนยัน`, or `ยืนยันรายการ` command.
The server derives the existing payload-bound, expiring confirmation token
internally; it is never sent to LINE/Facebook. Exact cancellation commands are
also supported. Arbitrary “yes” is not confirmation.

One external outbound Message has one `channel_message_deliveries` row:

- `PENDING`: persisted but provider acceptance is not confirmed.
- `SENT`: provider accepted the request; not proof of delivery/read.
- `FAILED`: send failed with a normalized safe error code.

Raw provider responses are not stored. `SENT` is never resent on webhook retry;
`PENDING` is not blindly duplicated; `FAILED` has no automatic infinite retry.
Webhook processing is synchronous in Sprint 9.0; there is no background channel
queue or asynchronous outbound worker.

Sprint 9.1 exposes connection status and role-aware configuration in the
Channels dashboard. The UI states the current text-only limitation, never
returns stored credentials, and shows safe recovery guidance for `ERROR`
connections. Provider webhook and outbound security rules remain unchanged.

## Manual LINE sandbox checklist

1. Create or select a LINE Developers Messaging API channel.
2. Generate a server-side channel access token and obtain the channel secret.
3. In Workspace Integrations, enter account ID, token, and secret; confirm they
   are cleared and never displayed after save.
4. Configure the HTTPS webhook URL shown by deployment convention:
   `/api/v1/channels/webhooks/line/{connection_id}`.
5. Enable webhook delivery and send a text message from a test LINE user.
6. Confirm one Customer/identity/conversation and one OneInFlow response.
7. Retry the same signed event and confirm no duplicate AI/outbound message.
8. Switch the conversation to `HUMAN`; confirm inbound persists but AI stops.
9. Send a staff reply in Inbox and confirm LINE receives it and delivery is
   `SENT`; test an invalid token and confirm UI/API reports `FAILED`.

## Manual Facebook sandbox checklist

1. Create/select a Meta developer app and test Page with Messenger enabled.
2. Generate a Page access token and securely obtain the App secret.
3. Generate a random verification token; save all values in Workspace
   Integrations and confirm secrets are not redisplayed.
4. Configure callback `/api/v1/channels/webhooks/facebook/{connection_id}` and
   complete the verification challenge.
5. Subscribe the Page to required messaging events and send a test text.
6. Confirm PSID identity mapping, one conversation, and one outbound response.
7. Replay the same `mid` and confirm no duplicate processing/send.
8. Verify Page echo events do not create customer messages or call AI.
9. Test `HUMAN` mode and an Inbox staff reply; inspect `SENT`/`FAILED` truth.

Real accounts and credentials are created manually and must never be stored in
the repository, documentation, logs, screenshots, or test fixtures.
