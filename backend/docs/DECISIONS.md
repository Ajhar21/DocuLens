# Architectural Decisions (Day 1)

1. **Synchronous SQLAlchemy 2.0 (`psycopg` v3)**
   - **Choice + Trade-off**: Use synchronous SQLAlchemy 2.0 with `psycopg` v3 instead of `asyncio` drivers for simpler transaction debugging, predictable connection pool behavior, and shared session code between FastAPI routes and the synchronous CPU/OCR worker; trades higher per-process concurrency under heavy I/O wait for simplicity and reliability.

2. **Database-Backed Job Queue with `FOR UPDATE SKIP LOCKED`**
   - **Choice + Trade-off**: Implement job queueing in PostgreSQL (`processing_jobs` with `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING`) instead of Redis/Celery to allow atomic document + job creation in a single DB transaction with zero external broker infrastructure; trades very high-throughput message dispatch for operational simplicity at low-to-moderate scale.

3. **Coarse RBAC via a Single Route Dependency (`require_role`)**
   - **Choice + Trade-off**: Enforce role checks (`admin`, `reviewer`, `viewer`, where `admin` always passes) using a single FastAPI dependency attached at the route/router level rather than permission tables or per-document ACLs; trades fine-grained resource authorization for clear, auditable access control.

4. **Local Disk Storage Behind a `StorageBackend` Interface**
   - **Choice + Trade-off**: Stream uploaded files to `STORAGE_DIR\documents\{document_id}\original{ext}` behind an abstract `StorageBackend` interface instead of coupling routes to `pathlib` or cloud SDKs; trades distributed multi-host file access today for zero-cost local development and a single-class swap to S3/GCS later.

5. **RapidOCR (`rapidocr-onnxruntime`) Behind an `OcrEngine` Interface**
   - **Choice + Trade-off**: Wrap `rapidocr-onnxruntime` (lazy-loaded once per worker process) behind an abstract `OcrEngine` interface; avoids external native binary installs (such as Tesseract system packages) or paid cloud OCR calls while allowing drop-in replacement with another OCR provider later.

6. **String Columns Validated by Python Enums**
   - **Choice + Trade-off**: Store `role`, document `status`, and job `status` as `VARCHAR` columns validated by Python `str, Enum` classes rather than native PostgreSQL `ENUM` types; trades DB-level enum type enforcement for frictionless schema evolution without `ALTER TYPE ... ADD VALUE` migration locks.

7. **Supabase Session Pooler (Port `5432`)**
   - **Choice + Trade-off**: Connect via the Supabase Session Pooler on port `5432` rather than the direct host or port `6543` transaction pooler; the direct host is IPv6-only on the free tier (unreachable on IPv4 networks), while the transaction pooler resets session state and breaks session-level `SET search_path`.

8. **Dedicated Test Schema (`TEST_SCHEMA`) in the Same Database**
   - **Choice + Trade-off**: Run `pytest` in a dedicated schema (`doculens_test`) on the same database instance instead of provisioning a second database; cheaper and zero-setup on free-tier hosting, with risk to dev data mitigated by a strict `TEST_SCHEMA` name guard and `SET search_path TO "<TEST_SCHEMA>", extensions` (never including `public`).

9. **PostgreSQL Extensions in the `extensions` Schema**
   - **Choice + Trade-off**: Install `vector` and `pg_trgm` in the dedicated `extensions` schema (`CREATE EXTENSION IF NOT EXISTS ... WITH SCHEMA extensions`) to match Supabase's managed convention and keep `public` and test schemas clean of extension objects; requires `extensions` to be included in `search_path` when extension operators/types are referenced.

10. **Row Level Security (RLS) Enabled with No Policies**
    - **Choice + Trade-off**: Enable RLS (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`) on all application tables with zero policies so Supabase's public PostgREST (`anon`/`authenticated`) roles are completely blocked by default, while the backend connects with the table-owner role which bypasses RLS.

11. **Store `sha256` Only (No Deduplication on Upload)**
    - **Choice + Trade-off**: Compute and persist the SHA-256 digest while streaming each file to disk without rejecting or deduplicating identical uploads on Day 1; keeps batch upload semantics simple and repeatable during testing, while leaving hash-based deduplication as future work.
