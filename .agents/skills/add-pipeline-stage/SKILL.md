---
name: add-pipeline-stage
description: Use when adding or modifying a stage of the DOCUMENT_PROCESSING pipeline or a new background job type. Covers idempotent stages, transactions, locked_at heartbeats, retryable vs non-retryable failures.
---

# Add or change a pipeline stage / job type

Rules from PRD 5.9. Code lives in `modules/jobs/`.

1. A stage is a function `stage(session, document_id, ctx) -> None` registered in `pipeline.py` in order. It must not know about polling.
2. **Idempotent**: inside one transaction, delete this stage's previous output for the document, then insert the new output. Running it twice gives the same rows.
3. After the stage commits, update `processing_jobs.locked_at` and `current_stage`.
4. Raise `RetryableError` for timeouts, 5xx, rate limits. Raise `NonRetryableError` for corrupt files, schema violations after retries, unsupported types. The runner maps these to backoff-retry vs `FAILED`, and writes `error_message`.
5. Never swallow errors into an "empty success". An OCR failure is a failure or a recorded warning, never silent empty text.
6. New job type: add the enum value, register a handler in `handlers.py`, and respect the partial unique index (one active job per document + type). The upload API must not change.
7. EMBEDDING-style jobs must not alter `documents.processing_status` on failure.
8. Tests (fake providers only): stage runs twice -> no duplicate rows; retryable failure -> `PENDING` with `run_after` in the future; attempts exhausted -> `FAILED`; stuck job recovery.

Do not add polling logic, brokers, or threads inside a stage.
