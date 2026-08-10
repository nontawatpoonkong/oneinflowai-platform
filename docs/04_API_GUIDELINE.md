Response Format

Pagination

Authentication

Status Code

Error Code

Versioning

Naming

WebChat

`POST /api/v1/webchat/sessions/{conversation_id}/messages`

```json
{"client_message_id":"browser-generated-id","content":"customer text"}
```

The response contains `conversation_id`, the persisted `customer_message`, and
an optional `assistant`. Types include `ANSWER`, `ACTION_COLLECTING`,
`ACTION_CONFIRMATION`, `ACTION_CREATED`, `ACTION_CANCELLED`, `HUMAN_MODE`,
`NO_RESPONSE`, and `ERROR`.

`POST /api/v1/webchat/sessions/{conversation_id}/action-collections/{collection_id}/confirm`

`POST /api/v1/webchat/sessions/{conversation_id}/action-collections/{collection_id}/cancel`

Both require the scoped WebChat token and a new `client_message_id`; confirm
also requires the current confirmation token. Public errors never expose prompts,
source content, vectors, secrets, provider payloads, or exception details.

Human operations

- `POST /api/v1/conversations/{id}/handoff`
- `POST /api/v1/conversations/{id}/assign` (omitting `assigned_user_id` means assign to me)
- `POST /api/v1/conversations/{id}/unassign`
- `POST /api/v1/conversations/{id}/return-to-ai`
- `POST /api/v1/conversations/{id}/read`
- `GET /api/v1/notifications`
- `POST /api/v1/notifications/{id}/read`
- `POST /api/v1/notifications/read-all`

All staff endpoints derive workspace and user identity from authentication.
Public WebChat can request handoff only through deterministic approved phrases;
it cannot select an assignee, return to AI, or mutate notification/read state.
