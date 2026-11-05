# DocuLens Backend (Day 1)

Backend service for **DocuLens**, an AI document intelligence system. Provides JWT authentication, coarse role-based access control (`admin`, `reviewer`, `viewer`), multi-file streaming uploads with header/magic-byte validation, a PostgreSQL-backed job queue (`FOR UPDATE SKIP LOCKED`), and document parsing for PDF, PNG/JPEG, XLSX, and CSV files.

## Database & Supabase Notes

- **Use the Supabase SESSION Pooler URL (port `5432`)** with the `postgresql+psycopg://` scheme in `backend\.env`.
  - Do **not** use the direct database host (IPv6-only on the Supabase free tier).
  - Do **not** use the transaction pooler on port `6543` (incompatible with session-scoped features such as `SET search_path`).
- **PostgreSQL Extensions**: `vector` and `pg_trgm` must be enabled in the `extensions` schema (`CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;` and `CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;`). The initial Alembic migration runs both statements idempotently.

## Windows `cmd.exe` Setup & Usage

Open `cmd.exe` and navigate to the `backend` directory:

```cmd
cd backend
```

### 1. Activate the Existing Virtual Environment

```cmd
venv\Scripts\activate
```

### 2. Install Direct Dependencies

```cmd
python -m pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the example environment file and fill in your Supabase Session Pooler `DATABASE_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`:

```cmd
copy .env.example .env
```

### 4. Run Database Migrations

```cmd
alembic upgrade head
```

### 5. Seed the Initial Admin User (Idempotent)

```cmd
python -m app.scripts.seed_admin
```

### 6. Start the FastAPI Server

```cmd
uvicorn app.main:app --reload
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`. Use the **Authorize** button with `ADMIN_EMAIL` and `ADMIN_PASSWORD` to authenticate.

### 7. Start the Background Worker

In a second `cmd.exe` window (with `backend\venv\Scripts\activate` active):

```cmd
cd backend
venv\Scripts\activate
python -m app.worker
```

To process a single job and exit:

```cmd
python -m app.worker --once
```

### 8. Run the Test Suite

Tests run in an isolated schema (`TEST_SCHEMA`, default `doculens_test`) with `search_path` restricted to `"<TEST_SCHEMA>", extensions`:

```cmd
pytest
```

## Day 2 — AI Extraction, Financial Validation & Embeddings

- **LLM Provider**: Google Gemini via `google-genai` (`LLM_MODEL=gemini-2.5-flash`, `LLM_TEMPERATURE=0`).
- **Embedding Provider**: `gemini-embedding-001` (`EMBEDDING_DIM=768`, L2-normalized in code, stored in `document_chunks.embedding` as `vector(768)` with an HNSW `vector_cosine_ops` index). Startup fails fast if `EMBEDDING_DIM` does not match the migration dimension (`768`).
- **OCR Confidence Threshold**: `OCR_LOW_CONFIDENCE_THRESHOLD` in `.env` controls when a `LOW_OCR_CONFIDENCE` (`INFO`) validation row is emitted; tune this value empirically on real scanned document samples.
- **Manual Smoke Script**:
  ```cmd
  cd backend
  venv\Scripts\activate
  python -m scripts.smoke_day2 <document_id>
  ```
