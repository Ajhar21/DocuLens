# Implementation Plan: DocuLens Background Processing Spike (Day 0)

## 1. Problem & Constraint Clarification

* **Objective:** Build a robust, production-grade background job execution engine spike for DocuLens in `backend/` without any external message broker (RabbitMQ/Redis/Celery), using PostgreSQL as the single source of truth for job states.
* **Scope Limits:**
  * Only `backend/` workspace code.
  * No authentication, no users table, no documents table, no frontend.
  * Windows cmd/PowerShell commands only.
* **Technical Constraints & Bounds:**
  * **Zero Broker Dependency:** PostgreSQL-backed queue via `processing_jobs` table (PRD 5.9).
  * **Concurrency & Locking:** Non-blocking row-level claiming with `SELECT ... FOR UPDATE SKIP LOCKED`.
  * **Driver & ORM Stack:** Synchronous SQLAlchemy 2.0 with the `psycopg` (v3) driver (`postgresql+psycopg://`) and Supabase connection pool resilience (`pool_pre_ping=True`).
  * **Async Event Loop Hygiene:** FastAPI runs an async event loop. To prevent blocking the single thread during sync SQLAlchemy database operations, HTTP routes that access the database must be standard `def` functions (which FastAPI dispatches to its internal `ThreadPoolExecutor`) or explicitly wrapped via `run_in_threadpool`.

---

## 2. Architectural Reasoning: Job Queue Mechanics

### Architectural Tradeoffs

| Dimension | Approach A: External Broker (Celery + Redis / RabbitMQ) | Approach B: PostgreSQL Row-Level Leasing (`SKIP LOCKED`) [Chosen] |
| :--- | :--- | :--- |
| **Infrastructure Overhead** | Requires separate service daemon, network port management, and monitoring. | Zero additional infrastructure. PostgreSQL is already provisioned. |
| **State Consistency** | Two sources of truth. If DB write fails after message ack (or vice versa), state drifts out of sync. | Single source of truth. Job status, lease timestamps, and error messages are ACID-consistent. |
| **Concurrency & Starvation** | Standard push/pull queues. Worker crashes require broker heartbeat management. | Native row-level locks via `FOR UPDATE SKIP LOCKED`. Workers skip claimed jobs with zero lock-wait time. |
| **Polling Overhead** | Minimal. | Polling cost is eliminated via partial index `(status, run_after) WHERE status = 'PENDING'` (pure index scan). |

### The Mental Model: Logical Leases & Safe Claiming
> **Why commit the claim *before* running the handler?**  
> Holding a database transaction open while a job executes (e.g. 30 seconds of OCR or LLM extraction) exhausts the database connection pool and blocks autovacuum. Instead, the worker claims the row, transitions it to `PROCESSING`, sets `locked_at = now()`, increments `attempt_count`, and **immediately commits**.  
> The worker now holds a *logical lease*. It issues heartbeats (`locked_at = now()`) across execution stages. If the worker process abruptly crashes (e.g., OOM, power cut), the lease expires, and the stuck-job recovery sweeper safely marks the job back to `PENDING`.

---

## 3. System Design & Data Contracts

### High-Level Architecture Flow

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client / Script
    participant API as FastAPI (app.main)
    participant DB as PostgreSQL (processing_jobs)
    participant Worker as Worker (app.worker)
    participant Runner as Job Runner (modules.jobs.runner)

    Client->>DB: enqueue(job_type, document_id) -> PENDING
    Worker->>DB: recover_stuck_jobs() -> resets timed-out PROCESSING rows
    Worker->>DB: claim() -> SELECT ... FOR UPDATE SKIP LOCKED
    DB-->>Worker: Row locked & returned
    Worker->>DB: UPDATE status='PROCESSING', locked_at=now(), attempt_count+=1; COMMIT
    Worker->>Runner: run_job(job_id)
    Runner->>Runner: Execute registered handler (dummy_handler)
    alt Handler succeeds
        Runner->>DB: complete_job(job_id) -> status='COMPLETED', completed_at=now()
    else Handler raises RetryableError (attempts < max)
        Runner->>DB: retry_job(job_id) -> status='PENDING', run_after=now()+backoff
    else Handler raises NonRetryableError or attempts exhausted
        Runner->>DB: fail_job(job_id) -> status='FAILED', error_message=...
    end
```

### Database Schema (`processing_jobs`)

| Column | Type | Constraints & Defaults | Notes |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | Primary Key, `server_default=text("gen_random_uuid()")` | Unique job ID |
| `document_id` | `UUID` | Nullable | Document identifier (FK added in Day 1) |
| `job_type` | `VARCHAR(50)` | NOT NULL, CHECK in (`DOCUMENT_PROCESSING`, `EMBEDDING`) | Job category |
| `status` | `VARCHAR(50)` | NOT NULL, DEFAULT `'PENDING'`, CHECK in (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`) | Lifecycle state |
| `attempt_count` | `INTEGER` | NOT NULL, DEFAULT `0` | Number of execution attempts |
| `run_after` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | Earliest execution timestamp |
| `locked_at` | `TIMESTAMPTZ` | Nullable | Timestamp of worker heartbeat/claim |
| `current_stage` | `TEXT` | Nullable | Active stage diagnostic |
| `error_message` | `TEXT` | Nullable | Captured stack/message on failure |
| `started_at` | `TIMESTAMPTZ` | Nullable | Execution start timestamp |
| `completed_at` | `TIMESTAMPTZ` | Nullable | Terminal completion or failure timestamp |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | Record creation timestamp |

#### Required Partial Indexes (from `docs/ERD.md` & `db-migration` skill):
1. **Queue Polling Index:**  
   `CREATE INDEX idx_processing_jobs_pending ON processing_jobs (status, run_after) WHERE status = 'PENDING';`
2. **Active Job Deduplication Index:**  
   `CREATE UNIQUE INDEX uq_processing_jobs_active_document_job ON processing_jobs (document_id, job_type) WHERE status IN ('PENDING', 'PROCESSING');`

---

## 4. Implementation Details

### Directory Tree to Create

```
backend/
├── .env                               # Live environment file (database credentials)
├── .env.example                       # Example environment file with documentation
├── pyproject.toml                     # Python dependencies and build config
├── alembic.ini                        # Alembic configuration
├── migrations/
│   ├── env.py                         # Alembic runner using app.core.config.settings
│   ├── script.py.mako
│   └── versions/
│       └── 0001_init_processing_jobs.py  # Extensions (vector, pg_trgm), table, partial indexes
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI application, GET /health, exception handling
│   ├── worker.py                      # Poll loop (python -m app.worker) with graceful shutdown & --run-once
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  # pydantic-settings: DATABASE_URL, worker tunables
│   │   └── responses.py               # Standard response envelope: { success, message, data, error }
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                    # DeclarativeBase
│   │   ├── session.py                 # Sync SQLAlchemy 2 engine with psycopg3, sessionmaker, get_db
│   │   └── models/
│   │       ├── __init__.py
│   │       └── job.py                 # ProcessingJob ORM model
│   └── modules/
│       ├── __init__.py
│       └── jobs/
│           ├── __init__.py
│           ├── exceptions.py          # JobError, RetryableError, NonRetryableError
│           ├── queue.py               # enqueue, claim (SKIP LOCKED), recover_stuck_jobs, heartbeat
│           ├── handlers.py            # JOB_HANDLERS registry with dummy_handler
│           └── runner.py              # run_job(job_id) entry point
├── scripts/
│   ├── __init__.py
│   └── enqueue_dummy_job.py          # CLI script to enqueue a dummy job
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Pytest test session & database fixtures
    └── test_jobs.py                   # Automated tests: claim, retry/backoff, stuck-job recovery
```

### Detailed Component Specifications

#### Step 1: Environment & Dependencies (`pyproject.toml` / `requirements.txt`)
* Dependencies to install:
  * `fastapi>=0.115.0`
  * `uvicorn[standard]>=0.30.0`
  * `pydantic-settings>=2.4.0`
  * `pydantic>=2.8.0`
  * `sqlalchemy>=2.0.30`
  * `psycopg[binary]>=3.2.0`
  * `alembic>=1.13.0`
  * `pytest>=8.0.0`
  * `httpx>=0.27.0`

#### Step 2: Core Configuration & Database Session
* `app/core/config.py`:
  * Subclasses `BaseSettings` (`model_config = SettingsConfigDict(env_file=".env", extra="ignore")`).
  * Normalizes `DATABASE_URL` (translating `postgresql://` into `postgresql+psycopg://` so SQLAlchemy explicitly selects the psycopg3 driver).
  * Exposes worker tunables:
    * `WORKER_POLL_INTERVAL_SECONDS: float = 2.0`
    * `WORKER_MAX_ATTEMPTS: int = 3`
    * `WORKER_BACKOFF_BASE_SECONDS: float = 5.0`
    * `WORKER_STUCK_JOB_TIMEOUT_SECONDS: int = 300`
* `app/core/responses.py`:
  * Implements `APIResponse[T](BaseModel, extra='forbid')` providing `{ success, message, data, error }`.
* `app/db/session.py`:
  * Sync SQLAlchemy 2.0 engine:
    ```python
    engine = create_engine(
        settings.sqlalchemy_database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    ```
  * Context manager `get_db_session()` for scripts/workers and generator `get_db()` for FastAPI dependencies.

#### Step 3: Database Models & Alembic Migration
* `app/db/models/job.py`:
  * Strongly-typed SQLAlchemy 2.0 model with `Mapped` and `mapped_column`.
* `alembic.ini` and `migrations/env.py`:
  * Configured to read the normalized `DATABASE_URL` from `settings` and import `Base.metadata`.
* `migrations/versions/0001_init_processing_jobs.py`:
  * `upgrade()`:
    1. Executes `CREATE EXTENSION IF NOT EXISTS vector;`
    2. Executes `CREATE EXTENSION IF NOT EXISTS pg_trgm;`
    3. Creates table `processing_jobs` with CHECK constraints.
    4. Creates partial index `idx_processing_jobs_pending` on `(status, run_after)` WHERE `status = 'PENDING'`.
    5. Creates partial UNIQUE index `uq_processing_jobs_active_document_job` on `(document_id, job_type)` WHERE `status IN ('PENDING', 'PROCESSING')`.
  * `downgrade()`:
    1. Drops indexes and table.
    2. Drops extensions conditionally (`DROP EXTENSION IF EXISTS pg_trgm; DROP EXTENSION IF EXISTS vector;`).

#### Step 4: Job Queue & Runner Implementation (`app/modules/jobs/`)
* `exceptions.py`:
  * `JobError(Exception)`
  * `RetryableError(JobError)` (network timeouts, transient rate limits)
  * `NonRetryableError(JobError)` (corrupted data, fatal errors)
* `queue.py`:
  * `enqueue(session, job_type, document_id=None, run_after=None) -> ProcessingJob`
  * `claim(session) -> Optional[ProcessingJob]`:
    * Runs:
      ```python
      stmt = (
          select(ProcessingJob)
          .where(ProcessingJob.status == "PENDING", ProcessingJob.run_after <= func.now())
          .order_by(ProcessingJob.run_after.asc(), ProcessingJob.created_at.asc())
          .with_for_update(skip_locked=True)
          .limit(1)
      )
      ```
    * If found: updates `status = 'PROCESSING'`, `locked_at = now()`, `started_at = started_at or now()`, increments `attempt_count`, commits immediately, and returns the job.
  * `recover_stuck_jobs(session, timeout_seconds, max_attempts) -> int`:
    * Finds `status == 'PROCESSING'` and `locked_at < now() - timeout_seconds`.
    * If `attempt_count >= max_attempts`: marks `status = 'FAILED'`, `error_message = 'Job timed out and exceeded max retry attempts'`.
    * Otherwise: marks `status = 'PENDING'`, `locked_at = None`, `run_after = now()`. Commits.
  * `heartbeat(session, job_id, current_stage=None)`: updates `locked_at = now()`, `current_stage = current_stage`.
  * `complete_job(session, job_id)`: sets `status = 'COMPLETED'`, `completed_at = now()`.
  * `retry_job(session, job_id, delay_seconds, error_message)`: sets `status = 'PENDING'`, `run_after = now() + delay_seconds`, `locked_at = None`, `error_message = error_message`.
  * `fail_job(session, job_id, error_message)`: sets `status = 'FAILED'`, `completed_at = now()`, `error_message = error_message`.
* `handlers.py`:
  * Registry `JOB_HANDLERS: dict[str, Callable]`.
  * `dummy_handler(job, session)`: logs simulated work, executes heartbeat, and returns successfully.
* `runner.py`:
  * `run_job(job_id) -> bool`:
    * Decoupled runner function.
    * Fetches job by ID. If not `PROCESSING`, exits.
    * Dispatches to handler.
    * Handles `RetryableError`: computes exponential backoff `base * 2^(attempts-1)`. If `attempts < max`, schedules retry; otherwise fails.
    * Handles `NonRetryableError` / generic exceptions: immediately marks `FAILED`.

#### Step 5: Worker CLI (`app/worker.py`)
* Implements poll loop around `run_job(job_id)`.
* Provides clean signal handling (`SIGINT`, `SIGTERM`).
* Supports `--run-once` flag for testing, CI, and batch processing.

#### Step 6: FastAPI Skeleton & Health Endpoint (`app/main.py`)
* Instantiates FastAPI application.
* Exposes `GET /health` with DB `SELECT 1` ping verification:
  ```json
  {
    "success": true,
    "message": "DocuLens API is healthy",
    "data": {
      "status": "healthy",
      "database": "connected",
      "environment": "development"
    },
    "error": null
  }
  ```

#### Step 7: Enqueue Script (`scripts/enqueue_dummy_job.py`)
* CLI script that enqueues a `DOCUMENT_PROCESSING` dummy job and prints its UUID, status, and scheduled time.

#### Step 8: Automated Pytest Suite (`tests/test_jobs.py`)
* `test_claim_job`: Verifies that `claim()` locks the job, increments `attempt_count`, and that a concurrent claim skips it.
* `test_retry_backoff`: Simulates a handler raising `RetryableError`, verifies that status returns to `PENDING` with future `run_after`, and checks that exceeding `max_attempts` transitions the job to `FAILED`.
* `test_stuck_job_recovery`: Simulates an abandoned `PROCESSING` job with expired `locked_at` and verifies that `recover_stuck_jobs` transitions it back to `PENDING`.

---

## 5. Hardening & Edge-Case Defenses

1. **Transient Connection Drops:** Supabase / cloud DB connection dropouts are mitigated with `pool_pre_ping=True` and connection recycles.
2. **Double Claims & Race Conditions:** Guaranteed zero race conditions using PostgreSQL row locking (`FOR UPDATE SKIP LOCKED`).
3. **Deadlocks:** Avoided because workers claim exactly 1 row per transaction and commit immediately.
4. **Zombie Jobs:** Unhandled worker crashes are reaped automatically by `recover_stuck_jobs`.

---

## Acceptance Verification Protocol

The spike will be verified strictly through the requested acceptance criteria:
1. `alembic upgrade head`
2. `python -m scripts.enqueue_dummy_job`
3. `python -m app.worker --run-once` (processes the dummy job to `COMPLETED`)
4. `python -m pytest -q` (all tests pass)
5. Live console output displayed for review.

