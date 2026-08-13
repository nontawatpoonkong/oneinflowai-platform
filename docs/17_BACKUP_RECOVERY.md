# Backup and Recovery

PostgreSQL is authoritative for business records and Knowledge chunk text. Redis is transient protection/state. Qdrant is a rebuildable vector index.

## PostgreSQL verified backup

Use a timestamped file outside the repository:

```bash
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > oneinflow.dump
docker compose exec -T postgres pg_restore -l < oneinflow.dump
```

Test every backup in an isolated database, never the application database:

```bash
docker compose exec -T postgres createdb -U "$POSTGRES_USER" oneflowai_restore_test
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d oneflowai_restore_test --clean --if-exists < oneinflow.dump
```

Point a one-off validation process at `oneflowai_restore_test`, run `alembic current`, and query a known non-sensitive table count. Drop only the isolated restore database after evidence is captured. Encrypt backups, restrict access, define retention externally and regularly test restore.

## Qdrant recovery

Do not restore Redis as business data. If Qdrant is lost, keep PostgreSQL online, recreate the configured collection and invoke the existing authenticated index operation for each READY Knowledge document. Indexing derives vectors from persisted exact chunks and removes stale points for that document. Validate semantic retrieval and citation resolution before reopening AI traffic. No automatic snapshot or bulk background re-index exists in the MVP.

## Recovery order

Restore configuration/secrets, PostgreSQL, run the expected application/Alembic version, restore Redis availability, rebuild Qdrant, then start backend/frontend and run readiness plus Pilot smoke flows.
