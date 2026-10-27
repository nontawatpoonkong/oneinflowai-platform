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
- `GET|PUT /workspaces/{workspace_id}/ai-instructions` (members may read;
  owner/admin may update)
- `PATCH /workspaces/{workspace_id}`
- `GET /workspaces/current/access`, `GET /workspaces/capabilities`
- `GET /workspaces/{workspace_id}/access-requests`
- `POST /workspaces/{workspace_id}/access-requests/{request_id}/approve|reject`
- `PATCH|DELETE /workspaces/{workspace_id}/members/{membership_id}`
- `PUT /workspaces/{workspace_id}/members/{membership_id}/capabilities`
- `GET|PATCH /workspaces/{workspace_id}/join-settings`
- `POST /workspaces/{workspace_id}/join-code/regenerate`
- `POST /workspace-access/resolve-code`, `POST /workspace-access/requests`
- `GET /workspace-access/my-requests`
- `POST /workspace-access/requests/{request_id}/cancel`
- `GET|POST /customers`, `GET|PATCH|DELETE /customers/{customer_id}`

Join-code resolution is authenticated and rate-limited, returns minimal
Workspace identity, and never creates membership. Approval atomically creates
membership plus validated code-defined capability grants.

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

`POST /payments/{payment_id}/verify` returns normalized Payment and verification
fields only. `GET /payments/{payment_id}/evidence` returns safe evidence metadata
without storage keys or file content. EasySlip credentials and raw responses are
never part of the public contract.

## Analytics

`GET /analytics/overview` accepts timezone-aware `start` and `end`, uses the UTC
half-open range `[start, end)`, and is restricted to entitled Workspace
owners/admins. Responses contain typed aggregates only and no customer content
or payment evidence.

`POST /analytics/events` accepts only authenticated, controlled `PAGE_VIEW`
telemetry. Workspace and user identity come from server context, the route must
be a normalized dashboard path, session/navigation identifiers are UUIDs, and
arbitrary properties are rejected.

## Audit

`GET /audit/events` and `GET /audit/events/{id}` require `audit.read`, apply the
trusted Workspace context, and return safe metadata only. List filters are
bounded and ordering is stable. There is no public create, edit, or delete audit
endpoint.

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
# Billing API

Billing endpoints are authenticated and scoped to the current Workspace:
`GET /billing/plans`, `/billing/subscription`, `/billing/entitlements`, and
`/billing/usage`. There is no public mutation, checkout, or self-upgrade API.
Quota failures use `ENTITLEMENT_QUOTA_EXCEEDED`; unavailable subscriptions and
capabilities use structured subscription/entitlement errors.

## Rich Hotel catalog API

Catalog endpoints live under `/api/v1/hotel/catalog`: reads require
`room.read`, while mutations require `room.manage`. The bounded calendar is
`GET /api/v1/hotel/availability-calendar?property_id=...&start_date=...&days=7|14|30`.
Each cell returns total, reserved, blocked, available, used, ratio, semantic
color bucket, inventory presence, and LOCAL/PMS authority. Clients must not
independently recalculate those critical values.

## Promotion API

Promotion administration and validation live under `/api/v1/promotions`.
Reads require `promotion.read`; mutations and lifecycle actions require
`promotion.manage`. `POST /validate` returns a deterministic result and safe
reason code, but is only a preview: Booking Hold always revalidates using
server-derived price, catalog, customer, Workspace, and source context.

Campaigns use explicit activate/pause/archive actions. Codes use explicit
disable/archive actions and are never hard-deleted after use. Public responses
contain no internal exception detail.

## Platform Administration API

All `/api/v1/platform/*` endpoints require `User.is_platform_admin`; Workspace
roles and `X-Workspace-ID` do not grant or choose platform query scope. Global
Users, Workspaces, subscriptions, campaigns, codes, attribution, and audit use
server pagination capped at 100. High-impact POST actions require `confirmed:
true` and a bounded reason. The API exposes no generic PATCH/DELETE, arbitrary
database search, impersonation, credentials, prompts, payment evidence, or
audit mutation endpoint.
