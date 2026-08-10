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
