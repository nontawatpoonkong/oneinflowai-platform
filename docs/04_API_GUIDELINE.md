# API guideline and implemented routes

Routes are versioned under the configured prefix, normally `/api/v1`. Protected
routes derive user/workspace identity from authentication and return the common
API response envelope. The list below reflects registered routers through
Sprint 9.0; it is not a list of planned APIs.

Sprint 9.1 adds no API route. Its Overview is a client-side operational
composition of the existing list endpoints. Action transitions, conversation
handoff/assignment, Knowledge rechunk/index operations, channel configuration,
and notification reads continue to use their existing authenticated APIs and
server-side authorization.

ActionDefinition management authorization:

- `GET /actions/definitions` and `GET /actions/definitions/{id}`: authenticated
  workspace members.
- `POST /actions/definitions` and `PATCH /actions/definitions/{id}`: workspace
  owner/admin only.
- No DELETE route. Lifecycle uses `is_active`; `key` is immutable after create.

## Auth

- `POST /auth/register`, `/auth/login`, `/auth/verify-email`
- `POST /auth/resend-verification`, `/auth/forgot-password`
- `POST /auth/verify-password-reset`, `/auth/reset-password`
- `GET /auth/me`

## Workspaces and customers

- `GET|POST /workspaces`, `GET /workspaces/me`
- `GET /workspaces/{slug}` (public lookup)
- `GET /workspaces/{workspace_id}/members`
- `PATCH /workspaces/{workspace_id}`
- `GET|POST /customers`, `GET|PATCH|DELETE /customers/{customer_id}`

## Conversations and messages

- `GET|POST /conversations`
- `GET|PATCH /conversations/{conversation_id}`
- `GET|POST /conversations/{conversation_id}/messages`
- `POST /conversations/{conversation_id}/handoff`
- `POST /conversations/{conversation_id}/assign` (omitting
  `assigned_user_id` assigns the authenticated caller)
- `POST /conversations/{conversation_id}/unassign`
- `POST /conversations/{conversation_id}/return-to-ai`
- `POST /conversations/{conversation_id}/read`

Assignment targets must already be members of the current workspace. Public
WebChat cannot choose an assignee, return a conversation to AI, or mutate staff
read/notification state.

## Notifications

- `GET /notifications`
- `POST /notifications/{notification_id}/read`
- `POST /notifications/read-all`

Results and mutations are restricted by both current workspace and recipient.

## WebChat

- `POST /webchat/sessions`
- `POST /webchat/sessions/{conversation_id}/messages`
- `GET /webchat/sessions/{conversation_id}/messages`
- `POST /webchat/sessions/{conversation_id}/action-collections/{collection_id}/confirm`
- `POST /webchat/sessions/{conversation_id}/action-collections/{collection_id}/cancel`

Sending, confirmation, and cancellation accept a new `client_message_id`; send
persists it as `Message.external_message_id`. Responses can include `ANSWER`,
`ACTION_COLLECTING`, `ACTION_CONFIRMATION`, `ACTION_CREATED`,
`ACTION_CANCELLED`, `HUMAN_HANDOFF`, `HUMAN_MODE`, `NO_RESPONSE`, or `ERROR`.
Sequential and concurrent duplicate requests recover their persisted result.

## Knowledge and RAG

- `POST /knowledge/upload`, `GET /knowledge`
- `POST /knowledge/search`, `/knowledge/rag-preview`, `/knowledge/answer`
- `GET /knowledge/{document_id}`, `/{document_id}/content`,
  `/{document_id}/chunks`
- `POST /knowledge/{document_id}/rechunk`, `/{document_id}/index`
- `DELETE /knowledge/{document_id}`

## Actions and Action Collection

- Action definitions: `POST|GET /actions/definitions`,
  `GET|PATCH /actions/definitions/{definition_id}`
- Queue: `POST|GET /actions`, `GET /actions/{action_id}`
- Lifecycle: `POST /actions/{action_id}/assign|start|complete|fail|cancel`
- Collection: `POST /action-collections`,
  `POST /action-collections/{collection_id}/input|confirm|cancel`, and
  `GET /action-collections/{collection_id}`

## Customer Payment

- `POST|GET /payments/destinations`
- `PATCH /payments/destinations/{destination_id}`
- `POST|GET /payments`, `GET /payments/{payment_id}`
- `POST /payments/{payment_id}/evidence`, `/{payment_id}/verify`
- `GET /payments/{payment_id}/verifications`

These APIs handle money paid by a customer to a workspace business. They are
not OneInFlow SaaS subscription billing APIs.

## Trust and error behavior

Public failures must not expose prompts, source documents, vectors, storage
paths, secrets, provider payloads, confirmation-token hashes, or internal
exceptions. Client-provided workspace/user identifiers are not trusted where
server-side authenticated/session context supplies the authority.

## Channel integrations

- `GET /channels`
- `POST /channels/line`
- `POST /channels/facebook`
- `GET|DELETE /channels/connections/{connection_id}`
- `POST /channels/webhooks/line/{connection_id}`
- `GET|POST /channels/webhooks/facebook/{connection_id}`

Configuration is workspace-admin-only and responses omit credentials. LINE
validates `X-Line-Signature`. Facebook performs its GET verification handshake
and validates POST `X-Hub-Signature-256`. Webhooks cannot choose a workspace or
supply trusted provider credentials.
