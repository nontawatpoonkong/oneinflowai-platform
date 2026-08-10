Authentication

Workspace

Customer

Conversation

Inbox

Knowledge

AI

Analytics

Billing

Settings

WebChat AI

- Public visitor sessions are authorized by a scoped session token.
- AUTO and COPILOT route active action collection before explicit action intent, then grounded knowledge answering.
- HUMAN mode does not invoke AI or action collection.
- ActionRequest creation requires a validated collection and explicit customer confirmation.
- Each send requires a conversation-scoped client message ID so safe retries return the original result.
- Citations and confirmation summaries use safe persisted Message metadata.

Human handoff and attention

- Exact customer phrases or an explicit staff action switch a conversation to HUMAN.
- Staff may self-assign or assign an existing workspace member.
- Return to AI is explicit and restores AUTO while clearing active handoff state.
- Customer messages create derived per-member unread work; AI messages do not.
- In-app notifications cover handoff, assignment, actions, and verified payments.
