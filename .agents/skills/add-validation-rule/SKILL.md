---
name: add-validation-rule
description: Use when adding or changing a deterministic financial validation rule or duplicate-detection logic in DocuLens. Rules are independent of extraction, configurable, and tested with Decimal math.
---

# Add a validation rule

1. Create a validator class in `modules/validation/validators/<name>.py` with `validate(invoice, context) -> list[Issue]`. It reads the persisted invoice only. It must not import from `extraction`.
2. `Issue` = `{code, field, message, expected_value, actual_value, severity}`. Codes are UPPER_SNAKE (for example `TOTAL_MISMATCH`).
3. Register it in `validation/orchestrator.py`. The orchestrator is the only place that knows the list of validators.
4. Use `Decimal` only. Compare with a configurable tolerance from `core/config.py` (and currency precision). Never `float`, never `==` on money.
5. Do not reject negatives globally (credit notes). Make that a config rule.
6. Duplicates: exact match on normalized supplier + invoice number + date + total. Flag for review; never delete or reject.
7. A missing field produces an issue, not an exception.
8. Severity `ERROR` or a low-confidence critical field makes `review_status = PENDING`. `WARNING` alone does not, unless config says so.
9. Tests: one passing case, one failing case, one tolerance-edge case, one null-field case per rule.
