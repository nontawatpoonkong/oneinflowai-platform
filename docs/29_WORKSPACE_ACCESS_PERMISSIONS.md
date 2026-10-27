# Workspace Access Requests and Granular Permissions

Sprint 10.9B adds a secure employee access lifecycle without coupling employee
membership to SaaS billing:

`join code → pending request → owner/admin review → membership + capability grants`

## Join codes

- Codes are high-entropy, regeneratable, disableable, and rate-limited.
- PostgreSQL stores only a lowercase SHA-256 digest and a four-character hint.
- Plaintext is returned only when regenerated; it is never logged or persisted.
- Resolution returns only the Workspace name and never lists Workspaces or
  exposes an internal Workspace UUID.
- A code creates a request only. It never creates membership.

## Access lifecycle

`WorkspaceAccessRequest` supports `PENDING`, `APPROVED`, `REJECTED`, and
`CANCELLED`. A partial unique index permits only one pending request per
user/Workspace, making repeated submissions idempotent. Approval locks the
request and atomically creates membership, stores explicit grants, records the
reviewer, and marks the request approved.

Owners may approve members or admins. Admins may approve members only. Neither
can approve their own request, review another Workspace's request, or approve a
reviewed request.

## Capability policy

`WorkspaceCapabilityService` remains the single authorization engine. Effective
access is `role baseline + WorkspaceMemberCapability grants`:

- Owner: every code-defined capability; authority cannot be stripped.
- Admin: broad Workspace operational and management capabilities, but no
  ownership transfer or platform-administration authority.
- Member: `dashboard.view` only, plus explicit Workspace-scoped grants.

Capability codes come from a closed registry. Unknown codes and cross-Workspace
membership IDs fail closed. Backend checks are authoritative; navigation
filtering is a UX convenience. Backend permission reads are authoritative on
every request, so revocation applies immediately.

Frontend presets such as Front Desk, Customer Service, Housekeeping, Payments,
and Read Only expand to ordinary capability codes. Presets are not stored roles.

Guest records (`/api/v1/customers`): listing and reading require `guest.read`;
creating, editing, and soft-deleting require `guest.manage` **and**
`guest.read` (write responses return the guest record). `guest.read` never
implies write access, and Workspace membership alone grants neither. Owners
and admins hold both through the role baseline; members need explicit grants,
and no frontend preset includes `guest.manage`. Successful writes append
`CUSTOMER_CREATED`, `CUSTOMER_UPDATED`, or `CUSTOMER_DELETED` audit events
(area `GUESTS`) carrying field names only, never guest names or contact data.
Booking payment exceptions (`GET /api/v1/hotel/payment-exceptions`) require
`payment.read`.

Customer 360 (`/api/v1/crm/customers`, `/{id}`, `/{id}/timeline`) requires
`guest.read`, which covers the guest profile only (contact details,
identities, tags, preferences, notes). Every other section is gated on its
own capability and is never queried without it: bookings, the repeat-guest
summary, and booking timeline events need `booking.read`; stays and stay
events need `stay.read`; conversation previews, conversation timeline events,
and the list's last-contact and needs-attention fields need
`conversation.read`; payments, payment exceptions, and payment events need
`payment.read`. Responses carry `bookings_visible`, `stays_visible`,
`conversations_visible`, and `payments_visible`, and hidden list fields are
`null`. The list filters `has_active_booking` and `repeat_guest` (booking),
`needs_attention` (conversation), and `has_payment_exception` (payment) are
rejected with 403 without the matching capability. A visible stay or payment
still names its booking id as a reference, without booking details.

Actions (`/api/v1/actions`) and Action Collections
(`/api/v1/action-collections`) use `action.read` and `action.operate`.
Owners and admins hold both through the role baseline; members need explicit
grants, and no frontend preset (including Read only) includes either.
`action.read` covers listing and reading Actions, Action Definitions, and
Action Collections. `action.operate` covers creating Actions and assigning,
starting, completing, failing, or cancelling them; these rows are locked while
they change, so concurrent requests cannot apply the same transition twice.
Operators without `action.read` receive a reduced Action response
(`details_visible: false`) without `payload`, `customer_id`,
`conversation_id`, or `idempotency_key`. Collection create, input, confirm,
and cancel need **both** `action.operate` and `action.read`, because each
returns the collected guest data and the confirmation summary staff must
review before confirming. Creating or changing Action Definitions stays
OWNER/ADMIN-only. Availability search (`POST /api/v1/hotel/availability/search`)
and quotes (`POST /api/v1/hotel/quotes`) require `room.read`.

An Action can only be assigned to a member who holds both `action.read` and
`action.operate`; otherwise the assignment is refused (422
`ACTION_ASSIGNMENT_INVALID`) before any state, event, or notification is
written. Linking a customer to an Action or Action Collection needs
`guest.read`, and linking a conversation needs `conversation.read`; both are
checked before the id is looked up, so callers without access cannot learn
whether it exists. Reading an Action Collection never writes: an overdue
session is reported as expired, and the next locked change (input, confirm,
or cancel) persists `EXPIRED`. Creating or changing an Action Definition
appends `ACTION_DEFINITION_CREATED` or `ACTION_DEFINITION_UPDATED` (area
`SETTINGS`) with the definition key, field keys, and changed field names
only, never names, descriptions, labels, or guest data. WebChat visitors are
not Workspace users: they confirm or cancel only collections of their own
conversation through their WebChat session token, and the resulting Action
credits no user.

AI tool results follow the capability of the data they carry, not
`conversation.read`: availability and room facts need `room.read`, promotion
checks `room.read` and `promotion.read`, booking holds `booking.read`, and
booking status, payment requests, and payment status need `booking.read` and
`payment.read`. Results a caller may not read come back as `null` with
`result_visible: false` in `/conversations/{id}/ai-actions`, and stored
results in message metadata (`ai_tool_result`) are withheld the same way in
`/conversations/{id}/messages`; new messages store only the AI tool action
id. `PAYMENT_VERIFIED` goes to the linked Action's assignee only while they
are a member holding `payment.read`, `action.read`, and `action.operate`,
otherwise to owners and admins.

Workspace billing needs `workspace.billing.read`: `/billing/entitlements`
and `/billing/usage` are rejected without it, except that `payment.read`
holders receive only the slip-verification quota from `/billing/usage`.
`/billing/subscription` returns the caller's own billing account
subscription, or the Workspace subscription only when the caller may read
that Workspace's billing; otherwise it returns no subscription.

Payment changes (destinations, payments, evidence, verification) need
`payment.review` and `payment.read`, since each returns the payment it
touched. Linking a customer, conversation, or Action to a payment needs
`guest.read`, `conversation.read`, or `action.read`, checked before the id is
looked up.

A conversation can be assigned, including at creation, only to a member who
holds `conversation.read`. Handoff and new-customer-message notices go to the
assignee while they still hold it; otherwise owners and admins receive them.
Creating a conversation needs `guest.read` for its customer, and a channel
connection must belong to the same Workspace.

Admin authority is owner-only: only the Workspace owner may appoint, demote,
re-grant, or remove an admin, or approve an access request as admin. Admins
and members holding `workspace.members.manage` may manage ordinary members
only, cannot change their own access, and cannot grant capabilities they do
not hold.

## Multi-Workspace behavior

Membership and grants are scoped independently. The frontend sends the selected
Workspace in `X-Workspace-ID`; the backend validates current membership before
resolving tenant context. Switching clears client query state and reloads access,
preventing Workspace A permissions or data from leaking into Workspace B.

## Audit and notifications

Immutable `workspace_access_audit_events` cover requests, review, cancellation,
grant/role changes, member removal, code regeneration, and join enablement.
Summaries contain safe state only and never a join code. New requests reuse the
existing Notification domain for Workspace owners/admins.

## API surface

Account routes:

- `POST /api/v1/workspace-access/resolve-code`
- `POST /api/v1/workspace-access/requests`
- `GET /api/v1/workspace-access/my-requests`
- `POST /api/v1/workspace-access/requests/{request_id}/cancel`

Workspace management includes current access, capability registry, request
review, member role/grant/removal, join settings, and join-code regeneration
under `/api/v1/workspaces`.

## Deliberate limits

- Ownership transfer and membership suspension are not implemented.
- Full audit-event UI is deferred; secure audit persistence exists.
- Existing notifications are Workspace-scoped, so approval/rejection is not
  shown as an account-level notification to a requester with zero Workspaces.
- Join codes are shared out of band; email invitation delivery is not included.
