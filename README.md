# OneInFlow

**Everything in one flow.**

OneInFlow is a multi-tenant customer-conversation platform that brings workspace administration, customer channels, conversations, and company knowledge into one product. The current codebase provides the secure platform foundation and grounded, citation-validated answer generation from workspace knowledge. It is not yet production-ready.

## Current architecture

The backend uses Python 3.12, FastAPI, Pydantic, async SQLAlchemy, Alembic, PostgreSQL, Redis, and Qdrant. Dependencies and commands are managed with `uv`. The frontend uses Next.js 15, React 19, TypeScript, Tailwind CSS, TanStack Query, Axios, `next-intl`, React Hook Form, and Zod.

```mermaid
flowchart LR
    UI["Next.js web application"] --> API["FastAPI API"]
    API --> PG["PostgreSQL"]
    API --> Redis["Redis"]
    API --> Qdrant["Qdrant vector index"]
    API --> RAG["Retrieval and RAG prompt package"]
    RAG --> Qdrant
    RAG --> PG
    RAG --> LLM["Generation provider"]
    LLM --> Validation["Citation validation and grounded answer"]
    API --> Queue["Action and fulfillment queue"]
    Queue --> Staff["Human fulfillment"]
    Channels["Additional customer channels"] -. "planned" .-> API
```

PostgreSQL is the source of truth for tenant-owned document and chunk data. Qdrant stores searchable vector records, while retrieval validates results against trusted PostgreSQL rows before returning them.

## Knowledge and RAG pipeline

The implemented pipeline is:

1. Upload a workspace-owned document.
2. Extract supported text content.
3. Create deterministic, bounded chunks and SHA-256 hashes.
4. Generate embeddings through a provider-neutral interface and index vectors.
5. Retrieve workspace-filtered candidates and validate them against PostgreSQL.
6. Assemble a bounded, deterministic context with stable source labels.
7. Build a provider-neutral prompt package that treats queries and sources as untrusted data.
8. Generate a bounded response through the configured provider.
9. Validate every citation against trusted RAG sources before returning a grounded answer.

The RAG preview API exposes the prepared context and user prompt for development and inspection. The answer API adds provider-neutral OpenAI or deterministic development generation, skips generation when no knowledge is available, and rejects missing or invented citations. Neither endpoint exposes the system prompt, vectors, storage paths, provider responses, or secrets.

## Multi-tenant security

- Workspace identity comes from authenticated server-side context, never a client-supplied workspace ID.
- Document, chunk, indexing, retrieval, and RAG operations are workspace-scoped.
- PostgreSQL ownership checks protect against stale, forged, or cross-workspace vector hits.
- Prompt construction labels retrieved content as untrusted reference data and prevents it from creating structural delimiters.
- Public API responses and operational logs avoid secrets, vectors, storage paths, document content, and internal exception details unless content is explicitly part of an authenticated knowledge response.

## Authentication

The backend includes registration, email OTP verification, login, token-based protected routes, and password-reset flows. Verification codes are delivered through an email-provider abstraction and are not returned as authentication credentials. Workspace and user dependencies enforce access at the API boundary.

## Conversation platform

The repository includes workspace, customer, conversation, message, AI-mode, and WebChat foundations. Grounded knowledge answers are available through the authenticated Knowledge API, but automatic WebChat or conversation replies are not implemented. Broader channel integrations remain future work.

## Action and fulfillment queue

The authenticated Action API supports reusable workspace-owned action definitions, strict structured payload validation, idempotent action creation, staff assignment, controlled status transitions, queue filtering, and atomic audit events. The implemented flow is structured business data → confirmed ActionRequest → fulfillment queue → human fulfillment.

Sprint 8.7 is manual-first. Grounded generation is not connected directly to database action creation, conversational AI field collection and confirmation remain future work, and `AUTOMATED` is metadata only. External API execution and Payment/Slip Verification are not implemented; payment is planned for Sprint 8.8 as a separate domain linked to an action request.

## Project structure

```text
backend/
  alembic/                 Database migrations
  app/
    ai/                    Provider-neutral AI foundations
    auth/                  Authentication flows and dependencies
    integrations/          Email, embedding, and Qdrant adapters
    knowledge/             Knowledge HTTP routes
    models/                SQLAlchemy domain models
    rag/                   Context assembly and prompt building
    repositories/          Persistence boundaries
    services/              Application workflows
  tests/                   Unit and PostgreSQL-backed integration tests
frontend/
  app/                     Next.js App Router pages
  components/              Product and shared UI components
  hooks/                   Client data and interaction hooks
  messages/                Localized copy
```

## Local development

Prerequisites: Python 3.12, `uv`, Node.js with npm, Docker, and Docker Compose.

```powershell
git clone <repository-url>
cd oneflowai-platform

cd backend
Copy-Item .env.example .env
uv sync
docker compose up -d postgres redis qdrant
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

On macOS or Linux, replace `Copy-Item .env.example .env` with `cp .env.example .env`. In another terminal:

```powershell
cd oneflowai-platform/frontend
npm install
npm run dev
```

The frontend defaults to `http://localhost:3000`; the API defaults to `http://localhost:8000`. Interactive OpenAPI documentation is available at `http://localhost:8000/docs` while the backend is running.

## Environment configuration

Copy `backend/.env.example` and configure values for the local environment. Important groups are:

- Application and security: environment, API prefix, signing secrets, allowed origins, and base-domain behavior.
- PostgreSQL and Redis: connection URLs used by the API and tests.
- Email: provider credentials and verification settings.
- Object storage: the configured document storage backend and limits.
- Embeddings and vector search: embedding provider/model, batch and dimension settings, Qdrant URL, collection, and retrieval limits.
- Chunking and RAG: chunk size/overlap, maximum chunks, maximum RAG sources, and context character budget.

Never commit real secrets. Use development providers only for local deterministic testing; production provider selection requires the corresponding credentials.

## Database migrations

Create schema changes through Alembic and keep exactly one current head:

```powershell
cd backend
uv run alembic current
uv run alembic heads
uv run alembic upgrade head
uv run alembic check
```

Generate a migration only when the persistent schema changes:

```powershell
uv run alembic revision --autogenerate -m "describe change"
```

Review generated migrations before applying them. The RAG context and prompt package are application-layer features and require no migration.

## Testing and quality checks

Backend lifecycle and transaction tests use PostgreSQL through `TEST_DATABASE_URL`; external providers are replaced with deterministic fakes.

```powershell
cd backend
$env:TEST_DATABASE_URL = "postgresql+asyncpg://oneflowai:oneflowai@localhost:5432/oneflowai_test"
uv run pytest -q
uv run ruff check .
```

Frontend checks:

```powershell
cd frontend
npm run lint
npm run build
```

## API overview

All application routes use the configured API prefix (normally `/api/v1`). Major route groups include authentication, workspaces, customers, conversations, messages, WebChat, AI mode, and knowledge management. Knowledge endpoints cover upload, content, chunks, indexing, semantic search, authenticated RAG preview, and grounded answers. Consult `/docs` for the exact request and response contracts of the running revision.

## Development status

Implemented:

- Multi-tenant users, workspaces, customers, and conversation foundations.
- Email-verification and password-reset authentication flows.
- Knowledge upload, extraction, deterministic chunking, hashing, and transaction-safe rechunking.
- Provider-neutral embeddings, Qdrant indexing, workspace-safe semantic retrieval, bounded context assembly, and deterministic prompt packaging.
- Provider-neutral grounded generation, zero-knowledge short-circuiting, normalized token usage, and strict citation validation.
- Generic manual Action/Fulfillment Queue with definitions, validation, assignment, lifecycle control, idempotency, and audit history.

In development:

- Product UI refinement and end-to-end conversation workflows.
- Operational hardening and expanded knowledge ingestion formats.

Planned:

- Automatic WebChat and conversation AI replies.
- AI conversational action collection and confirmation.
- Payment and slip-verification workflows (Sprint 8.8).
- Automatic external action execution.
- Additional customer messaging channels, asynchronous processing, expanded observability, and production deployment guidance.

## Design principles

- Tenant boundaries are enforced at every persistence and integration boundary.
- PostgreSQL remains authoritative; external indexes are treated as derived data.
- Determinism and idempotency make processing retryable and testable.
- Provider-neutral contracts keep external services replaceable.
- Security-sensitive inputs are untrusted by default and public failures remain sanitized.
- Changes stay within sprint scope and are backed by direct tests.

## MVP scope

The MVP targets a secure workspace-based customer-conversation foundation with managed knowledge ingestion and retrieval-ready context. It does not yet promise autonomous AI responses, every messaging channel, enterprise analytics, or a production hosted service.

## Naming compatibility

The product name is **OneInFlow**. The historical repository directory identifier `oneflowai-platform` may remain in local paths and clone instructions for compatibility; it is not the current product brand.

## License

License information has not yet been published.
