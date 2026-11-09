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

## Access control and user management

- **Central Permission Matrix (`app/core/permissions.py` & `src/lib/permissions.ts`)**: All backend routes depend on `require_permission(Permission.<NAME>)` resolved from a single `ROLE_PERMISSIONS` dictionary (`FINANCE_EXECUTIVE`, `FINANCE_MANAGER`, `ACCOUNTS_AUDIT`, `SYSTEM_ADMIN`), rather than scattering role-name comparisons across routers. *Trade-off*: Adding a new capability requires registering a `Permission` enum entry first, but eliminates authorization drift across endpoints.
- **Immediate Session Invalidation via `token_version` + `is_active`**: Every access JWT embeds `"tv": user.token_version`, and `get_current_user` verifies `user.is_active` and `user.token_version == payload["tv"]` against PostgreSQL on every request. *Trade-off*: Incurs one indexed primary-key lookup per authenticated request instead of purely stateless JWT validation, in exchange for immediate revocation on deactivation, role change, or password reset.
- **Idempotent Bootstrap & CLI Recovery (`app/seed.py` & `python -m app.create_admin`)**: Startup bootstrap seeds `ADMIN_EMAIL` / `ADMIN_PASSWORD` with `must_change_password=True` only when zero `SYSTEM_ADMIN` rows exist in the database, never overwriting an existing admin's password or status on boot. *Trade-off*: Changing `.env` credentials after initial setup no longer mutates the DB automatically; operators use `python -m app.create_admin` for explicit recovery.
- **Forced First-Login Password Rotation (`must_change_password`)**: Users flagged with `must_change_password=True` are blocked by `get_current_user` (`403 PASSWORD_CHANGE_REQUIRED`) on all routes except `/api/v1/auth/me`, `/api/v1/auth/logout`, and `/api/v1/auth/change-password`. *Trade-off*: Adds a dedicated dependency split (`get_current_user_allow_password_change` vs `get_current_user`), but guarantees bootstrap credentials cannot be used to access financial data.
- **Single-Use Hashed Invite & Reset Links (`user_action_tokens`)**: Inviting a user or requesting a password reset generates a 32-byte CSPRNG token (`secrets.token_urlsafe(32)`), stores only its SHA-256 hash with a configurable TTL (`INVITE_TTL_HOURS=72`), and returns the one-time link in the API response for clipboard copy. *Trade-off*: Avoids external SMTP/email dependencies in a single-tenant deployment while ensuring a database read-only leak cannot expose live invite or reset tokens.
- **Last-Admin & Self-Action Guardrails (`SELECT ... FOR UPDATE`)**: Role demotions and deactivations lock active `SYSTEM_ADMIN` rows in-transaction and reject self-demotion, self-deactivation, or removing the final active administrator (`409 Conflict`). *Trade-off*: Serializes concurrent admin-role mutations slightly via row locks, preventing race-condition lockouts of the tenant.
