# DocuLens Enterprise Test Cases Specification

**Document Version:** `v1.0.0` (Official Test Suite)  
**System Under Test:** DocuLens Document Ingestion & Extraction Engine  
**Companion Spreadsheet:** [`docs/DocuLens_Test_Cases.xlsx`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/docs/DocuLens_Test_Cases.xlsx)

---

## 1. Executive Summary & Test Strategy

DocuLens uses a **Hybrid Verification Strategy**:
* **Automated Unit & Integration Tests (Pytest + TestClient):** Covers deterministic business logic, auth policies, magic byte validation, streaming memory bounds, retry caps, and concurrency race conditions (`FOR UPDATE SKIP LOCKED`).
* **Manual / Smoke Validation (CLI + Swagger UI):** E2E verification of OCR visual readability, multi-sheet spreadsheet visual sanity, and real OS process interrupts (`Ctrl+C`).

### Test Coverage Matrix
| Module / Category | Count | Priorities | Primary Strategy |
| :--- | :---: | :---: | :--- |
| **Authentication & RBAC** | 4 | 3 × P0, 1 × P1 | Automated (`backend/tests/test_auth.py`) |
| **Core Ingestion & Parsing** | 3 | 2 × P0, 1 × P1 | Automated (`backend/tests/test_parsers.py`) |
| **OCR Quality & Engine** | 1 | 1 × P0 | Hybrid (`backend/app/processing/image.py` + sample inspection) |
| **Hostile Inputs & Boundary Defense** | 6 | 4 × P0, 2 × P1 | Automated (`backend/app/services/storage.py`) |
| **Queue, Workers & Concurrency** | 4 | 3 × P0, 1 × P1 | Automated & Hybrid (`backend/tests/test_queue.py`) |

---

## 2. Detailed Test Cases

### Group 1: Authentication & RBAC

#### `TC-AUTH-01`: User Login and JWT Access Token Generation
- **Priority:** `P0` (Blocker)
- **Preconditions:** User exists in DB with hashed password (`bcrypt`).
- **Steps:**
  1. Send `POST /api/auth/login` with form data: `username=reviewer@example.com`, `password=CorrectPass123!`.
  2. Verify HTTP `200 OK` response payload containing `access_token` and `token_type: "bearer"`.
  3. Send `GET /api/auth/me` with `Authorization: Bearer <access_token>`.
  4. Send `POST /api/auth/login` with incorrect password.
- **Expected Result:**
  - Valid login yields signed JWT token; `GET /api/auth/me` returns current user profile.
  - Invalid credentials immediately return `401 Unauthorized` with `"detail": "Incorrect email or password"`.
- **Automated Test:** `backend/tests/test_auth.py::test_login_success_and_failure`

---

#### `TC-AUTH-02`: Unauthenticated Access to Protected Endpoints
- **Priority:** `P0` (Blocker)
- **Preconditions:** Server running.
- **Steps:**
  1. Call `GET /api/documents` without `Authorization` header.
  2. Call `POST /api/documents` with invalid/expired token.
- **Expected Result:** HTTP `401 Unauthorized`. Zero business logic executed; no stack traces leaked.
- **Automated Test:** `backend/tests/test_auth.py::test_unauthenticated_and_malformed_tokens_rejected`

---

#### `TC-AUTH-03`: RBAC Permission Enforcement (Viewer Forbidden on Upload)
- **Priority:** `P0` (Blocker)
- **Preconditions:** User account with role `VIEWER`.
- **Steps:**
  1. Authenticate as `viewer@example.com`.
  2. Send `POST /api/documents` with a valid file.
  3. Send `GET /api/users` with viewer token.
- **Expected Result:** Both endpoints reject the request with HTTP `403 Forbidden` (`"Operation not permitted for role viewer"`). Only `REVIEWER` and `ADMIN` can upload documents.
- **Automated Test:** `backend/tests/test_auth.py::test_viewer_gets_403_on_upload_and_users`

---

#### `TC-AUTH-04`: Deactivated User Token Immediate Revocation Check
- **Priority:** `P0` (Critical Security)
- **Preconditions:** Active user logs in and obtains a valid JWT.
- **Steps:**
  1. Admin sets `user.is_active = False` in PostgreSQL.
  2. Deactivated user attempts to access `GET /api/auth/me` using their still-unexpired JWT.
- **Expected Result:** Returns HTTP `401 Unauthorized`. Access is immediately revoked because `get_current_user` performs a live check against `user.is_active` in the DB on every request.
- **Automated Test:** `backend/tests/test_auth.py::test_inactive_user_rejected`

---

### Group 2: Core Parsing & OCR Quality

#### `TC-PARSE-01`: Upload Clean Text-Layer PDF (Fast-Path, No OCR)
- **Priority:** `P0` (Blocker)
- **Preconditions:** Reviewer authenticated; worker running.
- **Steps:**
  1. Upload clean PDF with text layer (> 50 chars/page) to `POST /api/documents`.
  2. Worker processes document.
  3. Query `GET /api/documents/{id}` and check `parse_result`.
- **Expected Result:**
  - Status transitions `uploaded` $\rightarrow$ `processing` $\rightarrow$ `succeeded`.
  - `parse_result.ocr_used == false`.
  - `pages[0].source == "text_layer"`, `ocr_confidence == null`.
  - Text parsed accurately in <50ms without invoking OCR.
- **Automated Test:** `backend/tests/test_parsers.py::test_parse_text_layer_pdf_generated_in_test`

---

#### `TC-OCR-01`: Upload Scanned Image (JPG/PNG) & Validate OCR Readability
- **Priority:** `P0` (Critical)
- **Preconditions:** RapidOCR / Tesseract engine configured.
- **Steps:**
  1. Upload image file (`backend/OCR_test.jpg` or PNG scan) via `POST /api/documents`.
  2. Worker executes `handle_parse_job`.
  3. Inspect `parse_result` in DB or API.
- **Expected Result:**
  - `parse_result.ocr_used == true`.
  - `pages[0].source == "ocr"`.
  - Text is human-readable, containing target words (not just non-empty gibberish).
  - `pages[0].ocr_confidence` exists and is $\ge 0.40$.
- **Automated Test:** `backend/tests/test_parsers.py::test_ocr_on_real_image`

---

#### `TC-PARSE-02`: Semicolon CSV Parsing & Delimiter Detection
- **Priority:** `P1` (Normal)
- **Preconditions:** CSV with European semicolon formatting (`item;qty;price`).
- **Steps:**
  1. Upload semicolon CSV via `POST /api/documents`.
  2. Worker executes `parse_csv`.
- **Expected Result:**
  - Delimiter autodetected as `;` via `csv.Sniffer`.
  - Columns split cleanly: `["item", "qty", "price"]` (not a single joined string).
  - Data rows match table structure.
- **Automated Test:** `backend/tests/test_parsers.py::test_parse_csv_utf8_sig_and_semicolon_delimiter`

---

#### `TC-PARSE-03`: Multi-Sheet XLSX with Blank Columns & Empty Sheets
- **Priority:** `P1` (Normal)
- **Preconditions:** Multi-sheet Excel workbook where Sheet1 has missing header titles and Sheet2 is empty.
- **Steps:**
  1. Upload XLSX via `POST /api/documents`.
  2. Worker executes `parse_xlsx`.
- **Expected Result:**
  - Sheet1 generates clean synthetic column names (e.g., `["Invoice", "column_2", "Amount"]`).
  - Empty Sheet2 returns empty rows and columns without crashing `openpyxl`.
- **Automated Test:** `backend/tests/test_parsers.py::test_parse_xlsx_generated_with_blank_headers_and_empty_sheet`

---

### Group 3: Hostile Input & Boundary Defense

#### `TC-HOSTILE-01`: Corrupt File Upload (Garbage Bytes)
- **Priority:** `P0` (Blocker)
- **Preconditions:** Reviewer authenticated.
- **Steps:**
  1. Generate dummy file: `echo not a pdf > bad.pdf`.
  2. Upload to `POST /api/documents`.
- **Expected Result:**
  - Rejection at storage boundary because magic bytes do not start with `%PDF-`.
  - Response: `"status": "rejected"`, `"reason": "Invalid PDF signature (missing %PDF- header)"`.
  - If corrupt header bypasses upload, worker catches `DocumentParseError`, marks job and document `failed` with clean message, and worker **stays alive and healthy**.
- **Automated Test:** `backend/tests/test_parsers.py::test_corrupt_files_produce_clean_error`

---

#### `TC-HOSTILE-02`: Zero-Byte Empty File Upload (0 Bytes)
- **Priority:** `P0` (Blocker)
- **Preconditions:** Reviewer authenticated.
- **Steps:**
  1. Create 0-byte file: `type nul > empty.pdf`.
  2. Upload via `POST /api/documents`.
- **Expected Result:**
  - Batch upload response marks item `"rejected"` with reason `"File is empty (0 bytes)"`.
  - Never returns HTTP `500 Internal Server Error`.
  - Zero bytes written to storage; no job created.
- **Automated Test:** `backend/tests/test_documents.py::test_upload_zero_byte_file_rejected_cleanly`

---

#### `TC-HOSTILE-03`: Masquerading File Extension (.exe or .zip renamed to .pdf)
- **Priority:** `P0` (Security Blocker)
- **Preconditions:** An executable (`MZ...`) or zip archive renamed to `invoice.pdf`.
- **Steps:**
  1. Upload disguised binary to `POST /api/documents`.
- **Expected Result:**
  - Storage inspection reads first 4KB chunk and detects missing `%PDF-` signature.
  - Rejects with clear message: `"Invalid PDF signature"`.
  - Defends against polyglot and extension-spoofing attacks.
- **Automated Test:** `backend/tests/test_documents.py::test_multifile_upload_one_valid_one_invalid`

---

#### `TC-HOSTILE-04`: Oversized File Upload (Streamed Memory Boundary)
- **Priority:** `P1` (Critical)
- **Preconditions:** File larger than `MAX_UPLOAD_MB`.
- **Steps:**
  1. Post file stream larger than limit to `POST /api/documents`.
- **Expected Result:**
  - Storage service streams stream in 64 KB chunks.
  - When cumulative bytes exceed limit, raises `StorageValidationError` and removes partial temp file.
  - Does NOT load the whole file into RAM; server process remains under strict memory threshold.
- **Automated Test:** `backend/tests/test_documents.py::test_oversized_file_rejected_without_full_memory_load`

---

#### `TC-HOSTILE-05`: Password-Protected Encrypted PDF
- **Priority:** `P1` (Resilience)
- **Preconditions:** Encrypted PDF requiring password.
- **Steps:**
  1. Upload encrypted PDF.
  2. Worker invokes `parse_pdf`.
- **Expected Result:**
  - `fitz.open()` detects `doc.needs_pass` or `doc.is_encrypted`.
  - Immediately raises `DocumentParseError("PDF file is password-protected or encrypted")`.
  - Worker transitions job and document to `failed` without hanging or awaiting input.
- **Automated Test:** `backend/tests/test_parsers.py::test_password_protected_pdf_fails_fast`

---

#### `TC-HOSTILE-06`: Path Traversal, Spaces, & Unicode/Bangla Filenames
- **Priority:** `P0` (Security Blocker)
- **Preconditions:** Reviewer authenticated.
- **Steps:**
  1. Upload files named:
     - `..\..\..\etc\shadow.csv`
     - `চালান_২০২৬ invoice (1).csv`
     - `test name with spaces & symbols #$%.csv`
- **Expected Result:**
  - Physical file on disk is stored strictly at `documents/{uuid}/original.csv`.
  - Raw client filename is sanitized and stored only in DB metadata.
  - Traversal attempts are neutralized; Unicode/Bangla characters render correctly upon download.
- **Automated Test:** `backend/tests/test_documents.py::test_nasty_and_unicode_filenames_safe_path`

---

### Group 4: Queue & Worker Resiliency

#### `TC-QUEUE-01`: Worker Killed Mid-Job & Stale Heartbeat Recovery
- **Priority:** `P0` (Blocker)
- **Preconditions:** Job locked in `running` state by worker killed via `Ctrl+C` or pod crash.
- **Steps:**
  1. Simulate killed worker: `UPDATE processing_jobs SET status='running', locked_at = NOW() - INTERVAL '25 minutes'`.
  2. Start worker process or call `job_queue.requeue_stale(stale_minutes=10)`.
- **Expected Result:**
  - Stale job detected (`locked_at` expired).
  - Status reset to `pending`, `locked_by` and `locked_at` cleared to `NULL`.
  - Next available worker claims and processes the job to `succeeded`. Job is not lost.
- **Automated Test:** `backend/tests/test_queue.py::test_requeue_stale_running_jobs`

---

#### `TC-QUEUE-02`: Multi-Worker Concurrency (SELECT FOR UPDATE SKIP LOCKED)
- **Priority:** `P0` (Blocker)
- **Preconditions:** Multiple jobs queued; 2 workers polling simultaneously.
- **Steps:**
  1. Two concurrent threads invoke `job_queue.claim_next()` using a synchronization barrier (`threading.Barrier(2)`).
  2. Run query:
     ```sql
     SELECT document_id, count(*) FROM processing_jobs GROUP BY document_id HAVING count(*) > 1;
     ```
- **Expected Result:**
  - Exactly one worker claims the job; the other worker gets `None` or claims the next pending job.
  - Zero duplicate executions; query returns 0 rows.
- **Automated Test:** `backend/tests/test_queue.py::test_claim_next_concurrent_single_winner`

---

#### `TC-QUEUE-03`: Retry Limit Cap & Exponential Backoff
- **Priority:** `P0` (Blocker)
- **Preconditions:** Job configured with `max_attempts=3`.
- **Steps:**
  1. Force worker failure on attempt 1 $\rightarrow$ verify `status='pending'`, `attempts=1`, `run_after > NOW()`.
  2. Force failure on attempt 2 $\rightarrow$ verify backoff interval doubled.
  3. Force failure on attempt 3 $\rightarrow$ verify attempt reaches `max_attempts`.
- **Expected Result:**
  - Reattempts cease after max attempts.
  - Final job status is `failed` with `finished_at` timestamp.
  - Document status marked `failed` with `error` message. Worker does not loop infinitely.
- **Automated Test:** `backend/tests/test_queue.py::test_retry_backoff_and_max_attempts`

---

#### `TC-QUEUE-04`: Duplicate File Upload Handling (Design Decision)
- **Priority:** `P1` (Architectural Design)
- **Preconditions:** Reviewer authenticated.
- **Steps:**
  1. Upload `invoice.csv` $\rightarrow$ note `document_id_1` and `sha256`.
  2. Upload identical `invoice.csv` again $\rightarrow$ note `document_id_2`.
- **Expected Result:**
  - **Design Decision:** Allowed as separate instances.
  - Each upload receives a distinct UUID, its own storage directory, and an independent processing job.
  - `documents.sha256` records the hash for auditing and duplicate-flagging rules without blocking user workflow.
- **Automated Test:** `backend/tests/test_documents.py::test_duplicate_file_upload_allowed_with_hash_tracking`


---

## 3. How to Run & Maintain This Suite

### Automated Verification
Run the entire automated test suite:
```powershell
cd backend
python -m pytest -v --tb=short
```

### Full Migration & Sanity Smoke Test
```powershell
scripts\smoke.bat
```

### Updating the Excel Document
Whenever new pipeline stages or validation rules are added:
1. Update `backend/scripts/generate_test_cases_excel.py`.
2. Run:
   ```powershell
   backend\.venv\Scripts\python backend\scripts\generate_test_cases_excel.py
   ```
   The updated workbook will be generated at [`docs/DocuLens_Test_Cases.xlsx`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/docs/DocuLens_Test_Cases.xlsx).

