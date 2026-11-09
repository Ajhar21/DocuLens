# DocuLens — ERD

Based on PRD section 5.10 (14 tables). Render with any Mermaid viewer (GitHub, VS Code Mermaid extension, mermaid.live).

```mermaid
erDiagram
    roles ||--o{ users : "role_id"
    users ||--o{ refresh_tokens : "user_id"
    users ||--o{ user_action_tokens : "user_id"
    users ||--o{ documents : "uploaded_by"
    users ||--o{ document_corrections : "corrected_by"
    users ||--o{ reconciliation_jobs : "initiated_by"
    users ||--o{ audit_logs : "user_id"
    documents ||--o| document_parse_results : "document_id UNIQUE"
    documents ||--o| extracted_invoices : "document_id UNIQUE"
    extracted_invoices ||--o{ invoice_line_items : "invoice_id"
    documents ||--o{ validation_results : "document_id"
    documents ||--o{ document_corrections : "document_id"
    extracted_invoices ||--o{ document_corrections : "invoice_id"
    documents ||--o{ processing_jobs : "document_id"
    documents ||--o{ reconciliation_jobs : "source_document_id"
    documents ||--o{ reconciliation_jobs : "target_document_id"
    reconciliation_jobs ||--o{ reconciliation_results : "reconciliation_job_id"
    documents ||--o{ document_chunks : "document_id"

    roles {
        uuid id PK
        text name UK
        text description
    }
    users {
        uuid id PK
        text full_name
        text email UK
        text password_hash
        uuid role_id FK
        bool is_active
        bool must_change_password
        int token_version
        timestamptz last_login_at
        uuid invited_by FK
        timestamptz deactivated_at
        timestamptz created_at
        timestamptz updated_at
    }
    user_action_tokens {
        uuid id PK
        uuid user_id FK
        text token_type "INVITE | PASSWORD_RESET"
        text token_hash UK
        uuid created_by FK
        timestamptz expires_at
        timestamptz used_at
        timestamptz revoked_at
        timestamptz created_at
    }
    refresh_tokens {
        uuid id PK
        uuid user_id FK
        text token_hash UK
        uuid family_id
        timestamptz expires_at
        timestamptz revoked_at
        uuid replaced_by_id FK
        timestamptz created_at
    }
    documents {
        uuid id PK
        text original_filename
        text storage_path
        text mime_type
        bigint file_size
        text checksum UK
        text document_type
        text processing_status
        text review_status
        uuid uploaded_by FK
        uuid reviewed_by FK
        timestamptz reviewed_at
        timestamptz created_at
        timestamptz updated_at
    }
    document_parse_results {
        uuid id PK
        uuid document_id FK "UNIQUE"
        jsonb pages "[{page_number, text, source, ocr_confidence}]"
        jsonb tables "[{name, columns, rows}]"
        jsonb metadata
        bool ocr_used
        timestamptz created_at
    }
    extracted_invoices {
        uuid id PK
        uuid document_id FK "UNIQUE"
        text invoice_number
        date invoice_date
        text supplier_name
        text customer_name
        numeric subtotal
        numeric tax
        numeric total
        text currency
        jsonb extraction_metadata "raw LLM output, confidence, prompt version"
        timestamptz created_at
        timestamptz updated_at
    }
    invoice_line_items {
        uuid id PK
        uuid invoice_id FK
        int line_no "proposed"
        text description
        numeric quantity
        numeric unit_price
        numeric amount
    }
    validation_results {
        uuid id PK
        uuid document_id FK
        text validation_code
        text field_name
        text severity
        text message
        text expected_value
        text actual_value
        text status
        timestamptz created_at
    }
    document_corrections {
        uuid id PK
        uuid document_id FK
        uuid invoice_id FK
        text field_name
        text original_value
        text corrected_value
        uuid corrected_by FK
        text correction_reason
        timestamptz created_at
    }
    processing_jobs {
        uuid id PK
        uuid document_id FK
        text job_type
        text status
        int attempt_count
        timestamptz run_after
        timestamptz locked_at
        text current_stage "proposed"
        text error_message
        timestamptz started_at
        timestamptz completed_at
        timestamptz created_at
    }
    reconciliation_jobs {
        uuid id PK
        text reconciliation_type
        uuid source_document_id FK
        uuid target_document_id FK
        text status
        uuid initiated_by FK
        timestamptz created_at
        timestamptz completed_at
    }
    reconciliation_results {
        uuid id PK
        uuid reconciliation_job_id FK
        text field_name
        text source_value
        text target_value
        text comparison_status
        jsonb metadata
    }
    audit_logs {
        uuid id PK
        uuid user_id FK
        text action
        text entity_type
        uuid entity_id
        jsonb old_values
        jsonb new_values
        timestamptz created_at
    }
    document_chunks {
        uuid id PK
        uuid document_id FK
        int page_number "NULL for spreadsheets"
        int chunk_index
        text content
        tsvector content_tsv "generated"
        vector embedding "dim = configured model"
        text embedding_model
        timestamptz created_at
    }
```

## Column types

- All PKs `uuid` (default `gen_random_uuid()`).
- Money: `NUMERIC(19,4)`. Quantity: `NUMERIC(18,6)`. Never float.
- `invoice_date`: `date`. All timestamps: `timestamptz`.
- Status/type columns: `text` + CHECK constraint (easier to migrate than native PG enums).
- `reconciliation_jobs.source_document_id` / `target_document_id`: `ON DELETE RESTRICT` so reconciliation history survives (PRD principle 7).
- `audit_logs`: no FK cascade; append-only.
- `document_chunks.embedding`: `vector(N)`; N fixed by the pinned model. Table is created on Day 2 after the model is chosen.
- `reconciliation_results.source_value/target_value`: text, because they hold amounts, dates and strings.

## Indexes (PRD 5.10 principle 13)

| Table | Index |
|---|---|
| `document_chunks` | HNSW on `embedding` (`vector_cosine_ops`); GIN on `content_tsv`; B-tree on `document_id`; UNIQUE `(document_id, chunk_index)` |
| `extracted_invoices` | B-tree `invoice_number`, `invoice_date`, `total`; B-tree `lower(supplier_name)`; GIN `supplier_name gin_trgm_ops` |
| `documents` | `processing_status`, `review_status`, `uploaded_by`, `created_at`; UNIQUE `checksum` |
| `processing_jobs` | partial `(status, run_after)` WHERE status = 'PENDING'; **partial UNIQUE `(document_id, job_type)` WHERE status IN ('PENDING','PROCESSING')** |
| `validation_results` | `(document_id)`, `(validation_code)` |
| `document_parse_results` | UNIQUE `(document_id)` |
| `invoice_line_items` | `(invoice_id)` |
| `reconciliation_jobs` | `(source_document_id)`, `(target_document_id)`, `(status)` |
| `audit_logs` | `(entity_type, entity_id)`, `(user_id, created_at)`, `(action)`, `(created_at)` |
| `refresh_tokens` | UNIQUE `(token_hash)`, `(user_id)`, `(family_id)` |
| `users` | UNIQUE `(email)`, `(role_id)` |

## Additions & Deviations from PRD (small, each justified)

| Item | Why |
|---|---|
| `document_parse_results` + `document_chunks.page_number` (replaces `document_pages`, `spreadsheet_sheets`, `page_id`) | Day 1 stores parsed pages and spreadsheet tables as JSONB in a single `document_parse_results` row per document; `document_chunks` tracks `page_number` (`INTEGER NULL`) directly instead of a `page_id` FK. |
| `refresh_tokens` | Supports `POST /api/v1/auth/refresh` and `/logout` with SHA-256 hashed refresh tokens, token rotation (`replaced_by_id`), and family-based replay detection (`family_id`). |
| `documents.reviewed_by`, `reviewed_at` | PRD requires "approving user" in the audit; a column is cheaper to query than digging through `audit_logs`. Approval event still also goes to `audit_logs`. |
| `processing_jobs.current_stage` | Worker updates `locked_at` per stage; showing the stage in "processing history" costs one column. |
| `invoice_line_items.line_no` | Stable ordering of line items. |

Drop any of these if you want a strict PRD match.

## Things to watch

- Search filter `reconciliation_status` has no column on `documents`. Derive it with an `EXISTS` over `reconciliation_jobs` (source or target = document). Do not denormalize.
- `extracted_invoices` holds current (corrected) values. The original values live in `extraction_metadata` and `document_corrections`. Never overwrite without writing a correction row.
- Duplicate detection key: normalized supplier + invoice_number + invoice_date + total (exact). Index the first two for speed.
