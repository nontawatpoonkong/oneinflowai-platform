# Guest CRM and Customer 360 (Sprint 10.3)

Sprint 10.3 adds a Hotel-focused operational guest view. It is an aggregation
layer over OneInFlow's existing customer, conversation, booking, payment, and
payment-reconciliation domains; it is not a generic sales CRM or a replacement
for those authoritative domains.

## Source-of-truth boundaries

- `Customer` and `CustomerIdentity` remain the identity sources. Channel
  identities are displayed independently; this sprint does not merge people.
- `Conversation`, `Message`, assignment, handoff, and read-state rows remain the
  communication sources. Customer 360 returns bounded summaries, not message
  histories.
- `Booking`, `BookingItem`, and immutable `BookingEvent` rows remain the source
  for booking state, snapshots, and lifecycle history.
- `Payment` remains the source for verification and booking-application state.
  Existing reconciliation fields determine whether a verified payment is an
  unresolved exception. CRM does not create a second exception state.

No booking, payment, or conversation state is copied into CRM tables. There is
no denormalized Customer 360 cache in this MVP.

## CRM-owned data model

The `d6e7f8a9b0c1` migration adds five workspace-scoped tables:

- `customer_tags`: normalized tag definitions, unique by workspace and
  case-folded name.
- `customer_tag_assignments`: idempotent customer/tag links with the actor and
  creation time.
- `customer_preferences`: one current value per typed preference key and guest,
  including its explicit source.
- `customer_notes`: append-only operational staff notes.
- `customer_crm_events`: a narrow immutable audit stream for CRM-owned tag,
  preference, and note mutations.

Composite foreign keys include `workspace_id`, preventing a customer, tag, or
preference from being linked across workspaces. Existing `Customer.notes`
semantics are unchanged; new operational notes use `customer_notes`.

## Customer 360 composition

`Customer360Service` composes bounded sections for profile, identities, tags,
preferences, notes, conversation summaries, booking summaries, payment
summaries, unresolved payment exceptions, and a deterministic repeat-guest
summary. The detail endpoint defaults each growing section to 20 rows and caps
the requested limit at 100. Full conversation messages continue to use the
existing conversation APIs.

Payment output includes only safe operational metadata. Evidence storage keys,
content hashes, raw evidence, provider responses, credentials, and full account
data are never part of CRM responses.

## Tags, preferences, and notes

Owners and admins manage tag definitions and assignments. Names are trimmed,
case-folded for uniqueness, and assignment/removal is deterministic and
audited.

Preferences use a typed key and one of `CUSTOMER_PROVIDED`, `STAFF_CONFIRMED`,
or `IMPORT`. Provider or LLM output cannot use an `AI_INFERRED` source, and
deterministic validation remains authoritative. An upsert locks the customer
and records either `PREFERENCE_ADDED` or `PREFERENCE_UPDATED`.

Notes are append-only in this sprint. All workspace members may add an
operational note; there is no edit or delete route, avoiding unaudited history
rewrites. Note bodies do not appear in the timeline summary.

## Timeline

The journey timeline is assembled at read time from existing immutable booking
events, conversation timestamps, payment timestamps/state, and the new CRM
mutation audit events. Events are sorted by occurrence time, type, and stable
identifier before pagination. Queries are workspace- and customer-scoped and
bounded to 1,000 rows per source. This is not a generic event-sourcing system.

The current conversation model does not provide a durable event row for every
historic handoff or assignment transition, so the timeline shows current
conversation context and timestamps rather than inventing missing historic
events.

## Repeat-guest rule

A repeat guest is a customer with at least two `CONFIRMED` bookings in the same
workspace. Cancelled, expired, draft, held, and pending-payment bookings do not
increase that count. The response also reports confirmed/cancelled counts and
the latest booking date. It deliberately does not sum bookings across
currencies. The rule never assigns a VIP tag and does not use AI.

## Search and query behavior

`GET /api/v1/crm/customers` supports bounded pagination, name/email/phone
search, tag, active-booking, payment-exception, repeat-guest, and
needs-attention filters. Correlated aggregate and existence subqueries calculate
operational state in PostgreSQL, and tags are fetched once for the selected
page. The list does not issue one query per customer for bookings, payments, or
conversations.

## Authorization, PII, and tenancy

All endpoints require an authenticated workspace member. PII is returned only
after workspace membership and customer ownership checks. Members have
operational read access and may add notes and explicit preferences. Owners and
admins additionally manage tags. Every customer lookup includes
`workspace_id`; cross-workspace resources return not found, avoiding tenant
existence disclosure.

## API surface

- `GET /api/v1/crm/customers`
- `GET /api/v1/crm/customers/{customer_id}`
- `GET /api/v1/crm/customers/{customer_id}/timeline`
- `POST /api/v1/crm/customers/{customer_id}/notes`
- `POST /api/v1/crm/customers/{customer_id}/preferences`
- `PATCH /api/v1/crm/customers/{customer_id}/preferences/{preference_id}`
- `GET|POST /api/v1/crm/tags`
- `POST|DELETE /api/v1/crm/customers/{customer_id}/tags/{tag_id}`

The dashboard Guests page uses these APIs for real search/filter results and a
Customer 360 detail view with explicit preference/note entry and role-aware tag
controls. English and Thai copy is included.

## Known limitations and future Stay integration

This sprint does not include automated identity merge, PMS sync, stay/check-in
or check-out records, loyalty, marketing, predictive scoring, campaign tools,
generic pipelines, or AI-authored facts. Booking dates are not represented as a
completed Stay. A future Stay domain may add authoritative arrival, occupancy,
and departure events; Customer 360 should aggregate those records rather than
deriving stays from booking dates.
