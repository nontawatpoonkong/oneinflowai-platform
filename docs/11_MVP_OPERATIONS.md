# MVP Operations

Sprint 9.1 provides the staff-facing operational layer over contracts already
implemented by OneInFlow. It adds no database migration or aggregate dashboard
API.

## Information architecture

- **Overview**: current attention, open Action, ready Knowledge, pending Payment,
  connected Channel, and unread Notification counts plus recent conversations.
- **Inbox**: WebChat, LINE, and Facebook conversations with search, channel,
  AI-mode, attention, and unread filters; handoff, assignment, mode selection,
  message history, and truthful `PENDING`/`SENT`/`FAILED` outbound state.
- **Actions**: queue filters, structured payload details, assignment, supported
  lifecycle transitions, and links to the source conversation. Its Action Types
  tab lets owner/admin users configure the existing workspace ActionDefinitions;
  members see a read-only list.
- **Knowledge**: uploads, extraction/chunk status, vector-index status,
  transaction-safe rechunk retry, indexing, and deletion.
- **Payments**: Customer Payment records, safe evidence metadata, normalized
  EasySlip result, amount, masked destination, and timestamps. SaaS Billing is
  a separate domain.
- **Channels**: WebChat availability and LINE/Facebook connection status;
  owner/admin configuration with write-only secrets and text-only limitations.
- **Notifications**: recipient-scoped operational notifications with safe deep
  links and read controls.
- **Workspace / Settings**: workspace identity, current role, and member list.

## Authority and safety

The frontend does not reproduce business transitions or authorization rules.
All mutations use existing authenticated APIs, and the server remains
authoritative. Safe public error text is shown; credentials, provider payloads,
Action payloads, slip evidence, prompts, and internal exception details are not
surfaced in summaries or notifications.

## Action Type workflow

`ActionDefinition` → AI collection schema → missing-field collection →
deterministic validation → customer confirmation → `ActionRequest` → Queue.

The editor supports only backend field types: `string`, `integer`, `number`,
`boolean`, and `enum` with allowed values. Required and optional field order is
preserved in the JSONB arrays. Definition keys are editable only during create;
later lifecycle management uses enable/disable rather than deletion. The server
enforces workspace scope and owner/admin mutation authorization. The LLM cannot
invent an Action schema when no applicable active definition exists.

## Manual completion checklist

- Switch between English and Thai and visit every primary navigation route.
- Confirm loading, empty, safe error/retry, and populated states.
- Filter Inbox by text, channel, mode, attention, and unread; open a deep link.
- Hand off, assign, return to AI, send a staff reply, and inspect delivery state.
- Filter Actions, inspect structured fields, assign to self, and run only a
  server-supported transition.
- As owner/admin, create and edit an Action Type, reorder fields, configure enum
  values, and disable/re-enable it. Confirm a member sees no mutation controls.
- Upload a supported Knowledge file; inspect pipeline/index states; exercise
  rechunk/index recovery and delete confirmation.
- Inspect Payment states and masked destination data without exposing evidence.
- Confirm member roles cannot change Channel connections while owner/admin can.
- Open a Notification deep link and mark one/all notifications read.
- Verify tables and core operations remain usable at narrow viewport widths.

## Known limitations

Analytics is implemented for entitled owners/admins with explicit UTC ranges
and a separately labeled current queue snapshot. There is no Instagram, media messaging,
channel read receipt, automatic outbound retry, WebSocket, or background channel
processing in this sprint. Polling remains the current refresh mechanism.
