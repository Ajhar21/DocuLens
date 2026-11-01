---
name: db-migration
description: Use when creating or changing database tables, indexes, or extensions in DocuLens with Alembic. Covers pgvector/pg_trgm, the Day-2 document_chunks migration, partial indexes, and Windows commands.
---

# Database migration (Alembic, Windows)

1. Update the SQLAlchemy model in `db/models/`, then update `docs/ERD.md` in the same change.
2. Generate: `alembic revision --autogenerate -m "short message"` from `backend`. **Read the generated file.** Autogenerate misses extensions, partial indexes, generated columns, and vector types. Fix them by hand.
3. First migration enables extensions: `CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;`.
4. `document_chunks` is created only after the embedding model is chosen. Its `vector(N)` dimension must match `EMBEDDING_DIM` in config. Record the model in the README.
5. `content_tsv` is a generated column (`to_tsvector(...)` STORED). Indexes: GIN on `content_tsv`, HNSW with `vector_cosine_ops` on `embedding`.
6. Required partial indexes: unique `(document_id, job_type)` WHERE status IN ('PENDING','PROCESSING'); `(status, run_after)` WHERE status = 'PENDING'.
7. Status columns: `text` + CHECK constraint, not native enums.
8. Money: `NUMERIC(19,4)`. PKs: `uuid`. Timestamps: `timestamptz`.
9. Migrations must have a working `downgrade()` unless impossible; say so in the file.
10. Apply and verify: `alembic upgrade head`, then `alembic downgrade -1` and `alembic upgrade head` once.
11. Use a direct or session-mode `DATABASE_URL` for migrations. Transaction poolers break prepared statements. Set with `set DATABASE_URL=...`.
12. Changing the embedding model changes the dimension: new migration plus a re-embedding run, never a silent edit.
