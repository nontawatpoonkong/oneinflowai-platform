Project Name

OneInFlow

Product Type

AI Customer Communication Platform

Theme

Cyan White Black

Target

SME Thailand

Language

Thai First

Backend

FastAPI

Frontend

Next.js

Database

PostgreSQL

Vector DB

Qdrant

Coding Style

Clean Architecture

Dashboard

Business First

Never show CPU/RAM to customers.

Platform Admin has a separate dashboard.

WebChat AI

- AUTO/COPILOT: active collection first, explicit action intent second, grounded answering otherwise.
- HUMAN: no AI or action collection execution.
- AI output is untrusted; ActionRequest creation requires validation and explicit confirmation.
- Payment verification remains independent and cannot be controlled by AI.
- Conversation-scoped client IDs make sequential and concurrent retries idempotent.
- Message JSONB stores safe result metadata only, never prompts, full context, vectors, secrets, or confirmation-token hashes.
