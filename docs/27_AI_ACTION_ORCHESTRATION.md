# AI Action Orchestration

Sprint 10.7 adds a constrained bridge between customer conversations and
trusted hotel-domain services. It is not a generic autonomous agent. The AI
may select a code-defined tool and propose structured arguments, but it cannot
execute arbitrary code, issue arbitrary HTTP requests, write domain tables, or
grant itself a Workspace role.

## Authority boundary

The execution path is:

```text
customer message
-> intent and typed argument proposal
-> deterministic eligibility and schema validation
-> trusted Workspace/customer/entity resolution
-> explicit confirmation when required
-> authoritative domain service
-> typed tool result
-> safe customer response and audit
```

Model output is always untrusted. Workspace, customer, Conversation, Booking,
price, inventory, and payment-verification state are resolved or re-read by the
server. A tool handler calls the existing domain service; it does not reproduce
domain transitions or directly mutate the authoritative Booking, Payment,
inventory, or Conversation state.

The AI service principal has an explicit capability allowlist separate from
Owner/Admin/Member roles. It may search availability, read the current
customer's booking/payment state, create a customer-confirmed temporary hold,
request a customer-confirmed payment flow, and request human handoff. It may
not confirm a Booking, verify a Payment, change rates or inventory, check a
guest in/out, complete housekeeping, override room readiness, manage
automations, refund money, or run SQL/Python.

## Code-defined registry

`AIToolRegistry` contains immutable, versioned definitions. Each definition
declares its typed input/output models, safety classification, confirmation
policy, allowed Conversation modes, AI permission, extraction fields, and
handler. Tool definitions cannot be supplied by a Workspace or by a model.

Initial version `1` tools:

| Tool | Classification | Confirmation | Authority |
| --- | --- | --- | --- |
| `search_availability` | `READ_ONLY` | no | `HotelAvailabilityService` |
| `quote_availability` | `READ_ONLY` | no | `HotelAvailabilityService` |
| `get_booking_status` | `READ_ONLY` | no | `BookingService` plus trusted Payment state |
| `get_payment_status` | `READ_ONLY` | no | scoped Booking/Payment state |
| `create_booking_hold` | `MUTATING_SENSITIVE` | yes | `BookingService.create_hold` |
| `request_booking_payment` | `MUTATING_SENSITIVE` | yes | `BookingPaymentConfirmationService` |
| `handoff_to_human` | `MUTATING_REVERSIBLE` | no | `ConversationHandoffService` |

There is deliberately no `confirm_booking` or `verify_payment` tool.

## Eligibility and validation

Tools are eligible only in `AUTO` or `COPILOT`, for a trusted persisted
Conversation with a customer and an AI permission on the fixed allowlist.
Inputs use strict Pydantic contracts with unknown fields rejected. This also
prevents a model from injecting `workspace_id`, `customer_id`, or internal IDs.

Availability resolves active Property/RoomType/RatePlan records inside the
trusted Workspace. A hold requires a recent bounded availability result and
complete stay/occupancy data. The selected option is mapped to trusted IDs and
`BookingService` revalidates availability and authoritative pricing at
execution. Payment requests require the customer's current payable Booking and
an active Workspace payment destination. Status tools select only the current
customer's Workspace-scoped Booking and Payment.

## Confirmation and idempotency

Sensitive proposals are stored as `AWAITING_CONFIRMATION`. The confirmation is
bound to the action ID, Workspace, Conversation, customer, tool/version, exact
canonical payload hash, and expiry. Only a SHA-256 token hash is stored. The
default expiry is ten minutes and is bounded by configuration.

Confirmation must be presented by the same WebChat session. A changed payload,
expired token, different Workspace/Conversation/customer, cancelled action, or
invalid token fails closed. Repeating a valid confirmation after success
returns the same result. A database row lock and domain idempotency key ensure
concurrent confirmations cannot create a second hold or payment request.

The proposal itself has a Workspace-scoped idempotency key, so a duplicate
model/tool decision returns the existing action rather than executing twice.

## State and conversation context

`AIConversationState` stores only bounded structured state: selected property,
room and rate, requested dates and occupancy, active Booking, and at most ten
availability option identifiers. It is Workspace/Conversation scoped. It never
stores prompts, chain-of-thought, arbitrary model memory, credentials, or
payment evidence.

This state supports references such as "the first option" without treating raw
model memory as authority. Selection is still revalidated by domain services.
The per-turn tool-call budget is configurable but cannot exceed three; current
WebChat routing makes at most one tool decision for a customer message, so it
cannot recurse into an unbounded agent loop.

## Results, grounding, and precedence

Tool results are validated against typed output contracts before persistence
and customer display. Authority precedence is:

1. authoritative tool result;
2. structured domain data;
3. Knowledge/RAG descriptive evidence;
4. model prior.

A tool turn does not route its authoritative result back through unconstrained
generation. WebChat renders deterministic result text, preventing RAG or model
prior from contradicting current price, availability, Booking, or Payment
state. Ordinary non-tool messages retain the existing grounded-generation and
citation-validation path.

Verified payments that require review remain explicitly pending staff review;
the AI does not claim that the Booking is confirmed. Payment instructions come
only from the persisted Payment and PaymentDestination returned by the payment
service.

## Audit and observability

`AIToolAction` records the scoped proposal, exact validated payload/hash,
confirmation lifecycle, result reference, safe result, and normalized error
code. `AIToolAuditEvent` records `PROPOSED`, `CONFIRMED`, `EXECUTED`, `FAILED`,
`CANCELLED`, and `EXPIRED` with tool/version and safe status metadata.

Audit events never contain full prompts, model responses, secrets, credentials,
payment evidence, or confirmation tokens. The authenticated Conversation API
exposes structured action status/result but hides validated internal arguments,
payload hashes, and token hashes. Public WebChat exposes only the action card
needed for that session's confirmation.

## Failure behavior

Domain errors are normalized to safe `AI_TOOL_EXECUTION_FAILED` responses with
a bounded reason code; stack traces and internal exception text are not public.
Examples include unavailable inventory, ineligible Booking lifecycle, missing
Payment, or expired confirmation. Failed execution is persisted as `FAILED`
with a safe code and can be observed by staff. An explicitly unsupported or
low-confidence request continues through existing grounded response or handoff
behavior rather than invoking an unknown tool.

## Automation separation

AI orchestration never invokes Automation directly. It invokes the authoritative
domain service. That domain mutation may emit its normal outbox/domain event,
and Automation reacts through the existing event-driven boundary. An AI action
ID is not an Automation bypass.

## APIs

- `GET /api/v1/conversations/{conversation_id}/ai-actions` lists safe action
  status for authenticated Workspace staff.
- `POST /api/v1/webchat/sessions/{conversation_id}/ai-actions/{action_id}/confirm`
  confirms the exact pending payload using the WebChat session token.
- `POST /api/v1/webchat/sessions/{conversation_id}/ai-actions/{action_id}/cancel`
  cancels a pending action for the same session.

Natural explicit confirmation/cancellation messages use the same service and
guards. Existing WebChat message idempotency prevents retrying the message from
repeating intent, extraction, or execution.

## Example

1. Customer asks for two adults from January 1 to January 4.
2. `search_availability` returns current trusted options and totals.
3. Customer selects option 1 and asks to book.
4. `create_booking_hold` stores the exact trusted selection and asks for
   confirmation; no Booking exists yet.
5. Customer confirms before expiry.
6. `BookingService.create_hold` locks/revalidates inventory, prices the stay,
   and creates one idempotent temporary hold.
7. The deterministic response reports only the authoritative result.

## Known limitations

- The initial tool set is intentionally small and hotel-focused.
- WebChat uses one tool decision per customer turn; there is no autonomous
  multi-tool planner or recursive loop.
- Context is bounded structured selection state, not long-term agent memory.
- Staff observability is a status list rather than a full operational workflow
  editor.
- Tool responses are deterministic; blended post-tool generative prose is not
  enabled because authority and contradiction controls must remain explicit.
- External PMS/OTA operations, arbitrary integrations, check-in/out,
  housekeeping mutations, refunds, and autonomous Booking confirmation remain
  out of scope.
