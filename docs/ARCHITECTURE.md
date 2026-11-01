# DocuLens — Backend Modular Architecture

Source of truth: `docs/PRD.md` (v1.1). This file only maps the PRD to code.
Style: **modular monolith**. Two processes, one codebase: API (`uvicorn`) and worker (`python -m app.worker`). PostgreSQL is the only infrastructure.

## 1. Layout

```
backend/
  alembic.ini
  migrations/
  pyproject.toml
  .env.example
  app/
    main.py                     # FastAPI app factory, router mounting, error handlers
    worker.py                   # poll loop -> jobs.runner.run_job(job_id)
    core/
      config.py                 # pydantic-settings (ALL tunables live here)
      security.py               # password hashing, JWT encode/decode
      permissions.py            # Permission enum, ROLE_PERMISSIONS, require_permission(), RBAC_ENFORCEMENT flag
      visibility.py             # the ONE "who can see which documents" rule (list, file, search)
      responses.py              # {success, message, data, error} envelope
      errors.py                 # domain exceptions -> HTTP mapping
      logging.py
    db/
      base.py  session.py
      models/                   # one file per aggregate (users, documents, extraction, validation, reconciliation, jobs, audit, chunks)
      repositories/             # all SQL lives here; services never write raw queries
    modules/
      auth/                     # login, refresh, me
      users/                    # user CRUD, role assign, activate/deactivate
      documents/                # upload, file-type validation (magic bytes), checksum, list/detail, status
      storage/                  # Storage Protocol + LocalStorage
      processing/               # format processors -> unified content
        base.py                 # DocumentProcessor Protocol, UnifiedContent schema
        pdf.py                  # PyMuPDF text layer, flags low-text pages
        image_ocr.py            # images + scanned PDF pages
        spreadsheet.py          # xlsx/xls/csv (sheet + row traceability)
        ocr/                    # OCREngine Protocol, tesseract.py (TESSERACT_CMD), fake.py
        router.py               # picks processor by detected file type
      extraction/               # LLM -> validated invoice JSON
        prompts/                # versioned prompt files, no prompt strings elsewhere
        llm/                    # LLMProvider Protocol, <provider>.py, fake.py
        schemas.py              # Pydantic v2 InvoiceExtraction (Decimal amounts)
        batching.py             # page batching + merge rules
        normalizer.py           # dates, amounts, currency, supplier name
        service.py              # prompt -> LLM -> parse -> schema -> normalize -> persist
      validation/               # deterministic, no LLM
        orchestrator.py
        validators/             # required.py numeric.py calculation.py duplicate.py
        config.py               # tolerances, rules toggles
      review/                   # review queue, corrections, approve/reject
      reconciliation/           # independent of extraction
        service.py  matchers.py # normalized exact / tolerance / not-comparable
        pdf_pdf.py  pdf_excel.py  mapping.py
      jobs/
        queue.py                # enqueue, claim (FOR UPDATE SKIP LOCKED), lease, backoff, stuck-job recovery
        runner.py               # run_job(job_id): the single entry point
        handlers.py             # JOB_HANDLERS = {DOCUMENT_PROCESSING: ..., EMBEDDING: ...}
        pipeline.py             # DOCUMENT_PROCESSING stages
      embeddings/               # EmbeddingProvider Protocol, chunker.py, service.py, fake.py
      search/                   # keyword.py semantic.py hybrid.py(RRF) filters.py service.py
      audit/                    # AuditService.record(...)
      stats/                    # dashboard counters
    api/v1/                     # thin routers only: auth users documents reviews reconciliation search jobs stats
    evaluation/                 # standalone CLI: dataset.py metrics.py run.py (extraction + retrieval)
  tests/{unit,integration,api,fixtures}
eval_data/
  labeled/                      # real docs + ground-truth JSON
  retrieval_queries.json
```

## 2. Module responsibilities and dependencies

| Module | Owns | May depend on |
|---|---|---|
| `api/v1` | HTTP, envelope, `Depends(require_permission(...))` | module services only |
| `auth`, `users` | identity, user CRUD | db, core |
| `documents` | upload, file validation, checksum, metadata, list/detail | storage, jobs.queue, audit, core.visibility |
| `storage` | save/open/delete file bytes | nothing |
| `processing` | file -> `UnifiedContent` (pages or sheets + warnings) | `ocr` only. No DB, no LLM |
| `extraction` | text -> validated, normalized invoice | `llm`, db (own tables) |
| `validation` | rules -> issues, duplicate candidates | db (read invoices), config |
| `review` | corrections, approval, review_status transitions | validation (re-run), audit, db |
| `reconciliation` | compare two stored extractions / PDF vs sheet | db (read only on extraction + sheets) |
| `jobs` | queue mechanics, `run_job`, stage orchestration | processing, extraction, validation, embeddings, db |
| `embeddings` | chunk + embed page text | provider, db |
| `search` | keyword/semantic/hybrid, filters | embeddings (query vector), core.visibility, db |
| `audit` | append-only audit_logs | db |
| `stats` | counters | db |

Hard rules (enforce in review):
- `processing`, `ocr`, `llm`, `embeddings`, `storage` never import from `db`, `api`, or other business modules.
- `reconciliation` never imports `processing` or `extraction`. It reads persisted results.
- `validation` never imports `extraction`. It reads persisted results.
- Routers contain no logic beyond parse request -> call service -> wrap response.
- Services never build SQL; repositories never raise HTTP errors.

## 3. Job system (PRD 5.9)

- Table `processing_jobs`; types `DOCUMENT_PROCESSING`, `EMBEDDING`.
- Claim: oldest `PENDING` with `run_after <= now()`, `FOR UPDATE SKIP LOCKED`, set `PROCESSING`, `locked_at`, `attempt_count += 1`, **commit before working**.
- Update `locked_at` after each stage. Stuck `PROCESSING` older than timeout -> back to `PENDING` (counts as an attempt).
- Retryable failure + attempts left -> `PENDING` with `run_after = now + backoff`. Else `FAILED` with `error_message`.
- Partial unique index: one active (`PENDING`/`PROCESSING`) job per `(document_id, job_type)`.
- Admin retry: `FAILED -> PENDING`, reset `run_after`. Never creates a new document row.
- `run_job(job_id)` knows nothing about polling. The worker loop is a thin driver, so a broker can replace it later.

### DOCUMENT_PROCESSING stages (each stage = one transaction, replaces only its own output)

1. **parse** -> `document_pages` or `spreadsheet_sheets`. PDF: text layer per page, pages under a min-char threshold go to OCR. Images: OCR. OCR failure becomes a recorded warning/failure, never an empty success.
2. **extract** (PDF and image only) -> `extracted_invoices` + `invoice_line_items`. Page batches -> LLM -> merge -> normalize. Raw LLM output saved in `extraction_metadata`.
3. **validate** -> `validation_results` (required, numeric, calculation, duplicate).
4. **decide** -> `review_status` = `PENDING` if any error-severity issue or low-confidence critical field or warnings needing a human, else `NOT_REQUIRED`. Set `processing_status = COMPLETED`. Enqueue `EMBEDDING` if the document has page text.

Spreadsheets stop after stage 1: they are reconciliation targets, not invoices (assumption, see section 6).

### EMBEDDING job
Chunk `document_pages.extracted_text` -> embed -> write all chunks in one transaction. Failure never touches document `processing_status`.

## 4. RBAC seam (initial mode: admin-only)

Build the seam now, defer the enforcement.

- Real login and JWT from day 1. `uploaded_by`, `corrected_by`, `audit_logs.user_id` need a real user identity.
- Seed 4 roles, seed one `admin` user.
- `core/permissions.py` defines the `Permission` enum and full `ROLE_PERMISSIONS` map from PRD 3.5 now (about 30 lines).
- Every route declares `Depends(require_permission(Permission.X))` from the first endpoint.
- `RBAC_ENFORCEMENT=false` (default during build): `require_permission` always allows. `core/visibility.py` returns "all documents".
- Before Day 4: set `true`, run one parametrized test over the matrix, fix what breaks.

Trade-off: the seam costs a few minutes per endpoint and avoids a retrofit across ~40 routes. PRD F-01 is P0 and acceptance section A requires enforcement, so this cannot be dropped, only postponed.

## 5. Search design (PRD 5.11)

One SQL pipeline: `visible_documents(user)` AND filters -> candidate doc ids -> keyword list and semantic list over chunks of those docs -> RRF -> best chunk per doc -> paginate.
- Keyword: `ts_rank` on `content_tsv`, plus exact-match boost on invoice number / supplier (pg_trgm for supplier similarity).
- Semantic: cosine on `embedding`, `embedding_model = settings.EMBEDDING_MODEL`, similarity >= `SEMANTIC_MIN_SIMILARITY`.
- Hybrid: if query embedding fails, return keyword results plus `warning`.
- Filter-only (no `q`): order by `created_at desc`.
- Structured fields come from `extracted_invoices` (current, corrected values).
- Response includes keyword rank, semantic similarity, combined score.

## 6. Decisions I made where the PRD is silent (change if you disagree)

1. One invoice per document in MVP (`extracted_invoices.document_id` unique). Multi-invoice PDFs are out of scope.
2. Multi-page merge rule (proposal, verify on real multi-page samples): header fields = first non-null across batches; line items = concatenated; totals = from the batch with highest reported confidence.
3. Spreadsheets skip LLM extraction and validation; `review_status = NOT_REQUIRED`.
4. Duplicate file upload (same checksum): reject with HTTP 409 and the existing document id.
5. After a correction, the review service re-runs the deterministic validators synchronously (no OCR/LLM/embedding, so it does not violate the "no heavy work in handlers" rule).
6. Processing history in the UI = `processing_jobs` rows + `audit_logs`. No extra table.
