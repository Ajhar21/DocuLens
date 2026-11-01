---
name: run-evaluation
description: Use when building, running, or reporting DocuLens extraction or retrieval evaluation. Metrics must come from the labeled dataset; never invent numbers.
---

# Run and report evaluation

Hard rule: **no number appears in any report unless `app/evaluation` produced it in this run.** No labeled data or no run means "not yet measured".

1. Dataset: `eval_data\labeled\` holds real documents plus ground-truth JSON (one per document). Cover digital PDFs, scanned PDFs, images, Excel, CSV, multi-page, and documents with known financial inconsistencies. Retrieval queries: `eval_data\retrieval_queries.json` with expected document ids (exact-match, semantic, filter-combined).
2. Run (cmd.exe, from `backend`): `python -m app.evaluation.run --dataset ..\eval_data\labeled --out ..\eval_data\report.json`
3. Extraction metrics: field accuracy (correct / evaluated fields), exact-invoice accuracy, validation detection rate, false positive rate, success/failure rate, manual review rate, straight-through rate, processing time (measured upload to completion).
4. Retrieval metrics: precision@k and recall@k reported **separately for keyword, semantic, hybrid**.
5. Use the results to set `DEFAULT_SEARCH_MODE` and `SEMANTIC_MIN_SIMILARITY` in config. Record the values and the run date.
6. Comparison is on normalized values (Decimal amounts, ISO dates, normalized names). Document the normalization.
7. Output the failure list (document, field, expected, got). Failures are the useful part.
8. The report states dataset size, which provider/model was used, and the date. Small dataset: say so; do not extrapolate or claim production accuracy.
9. Live LLM/embedding calls are allowed in the eval CLI only, never in the pytest suite.
