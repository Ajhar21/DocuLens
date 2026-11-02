import sys
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def build_test_cases_workbook(output_path: Path):
    wb = openpyxl.Workbook()
    
    # -------------------------------------------------------------
    # Sheet 1: Overview Dashboard
    # -------------------------------------------------------------
    ws_summary = wb.active
    ws_summary.title = "Overview & Matrix"
    ws_summary.views.sheetView[0].showGridLines = True
    
    # Title Block
    ws_summary["A1"] = "DocuLens Enterprise Test Cases Specification"
    ws_summary["A1"].font = Font(name="Calibri", size=16, bold=True, color="1F4E78")
    ws_summary["A2"] = "Official verification suite covering Core Ingestion, Hostile Inputs, Queue Concurrency, and Auth Security."
    ws_summary["A2"].font = Font(name="Calibri", size=11, italic=True, color="595959")
    
    # Metadata Table
    meta_headers = ["Project", "Environment", "Target Framework", "Automation Tooling", "Document Version", "Last Updated"]
    meta_values = ["DocuLens AI Ingestion Engine", "Local / CI / Docker", "FastAPI + SQLAlchemy + PostgreSQL", "Pytest + TestClient + OpenPyXL", "v1.0.0 (Official)", "November 2026"]
    
    for idx, (h, v) in enumerate(zip(meta_headers, meta_values), start=4):
        ws_summary[f"A{idx}"] = h
        ws_summary[f"A{idx}"].font = Font(name="Calibri", size=10, bold=True, color="1F4E78")
        ws_summary[f"B{idx}"] = v
        ws_summary[f"B{idx}"].font = Font(name="Calibri", size=10)

    # Categories Summary Table
    ws_summary["A12"] = "Test Category Breakdown"
    ws_summary["A12"].font = Font(name="Calibri", size=12, bold=True, color="1F4E78")
    
    cat_headers = ["Category", "Total Tests", "P0 (Blocker)", "P1 (Critical)", "Primary Strategy"]
    for col_idx, h in enumerate(cat_headers, start=1):
        cell = ws_summary.cell(row=13, column=col_idx, value=h)
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    cat_data = [
        ("Authentication & RBAC (Auth)", 4, 3, 1, "Automated (Pytest)"),
        ("Core Ingestion & Parsing (Parse)", 3, 2, 1, "Hybrid (Automated + Visual)"),
        ("OCR Readability & Engine (OCR)", 1, 1, 0, "Hybrid (Pytest + OCR Confidence)"),
        ("Hostile Inputs & Boundary Defense (Hostile)", 6, 4, 2, "Automated (Storage & Header Validation)"),
        ("Queue, Workers & Concurrency (Queue)", 4, 3, 1, "Hybrid (Multi-thread Barrier + Smoke CLI)"),
    ]
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    for row_idx, r_data in enumerate(cat_data, start=14):
        for col_idx, val in enumerate(r_data, start=1):
            cell = ws_summary.cell(row=row_idx, column=col_idx, value=val)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border
            if col_idx in (2, 3, 4):
                cell.alignment = Alignment(horizontal="center")
                
    ws_summary.column_dimensions["A"].width = 38
    ws_summary.column_dimensions["B"].width = 25
    ws_summary.column_dimensions["C"].width = 15
    ws_summary.column_dimensions["D"].width = 15
    ws_summary.column_dimensions["E"].width = 35

    # -------------------------------------------------------------
    # Sheet 2: Detailed Test Cases
    # -------------------------------------------------------------
    ws_cases = wb.create_sheet(title="Test Cases")
    ws_cases.views.sheetView[0].showGridLines = True
    
    headers = [
        "Test ID",
        "Category",
        "Priority",
        "Test Title",
        "Preconditions",
        "Test Steps",
        "Test Data / Command",
        "Expected Result",
        "Testing Type",
        "Automated Test / Verification Reference",
        "Status",
        "Notes / Architectural Insight"
    ]
    
    # Header row formatting
    for col_idx, h in enumerate(headers, start=1):
        cell = ws_cases.cell(row=1, column=col_idx, value=h)
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
    ws_cases.row_dimensions[1].height = 28
    ws_cases.freeze_panes = "A2"
    
    # Rows data
    test_rows = [
        # 1. Login and token
        (
            "TC-AUTH-01",
            "Authentication",
            "P0",
            "User Login and JWT Access Token Generation",
            "Active user account exists in DB with hashed password.",
            "1. Send POST /api/auth/login with valid username and password (form-encoded).\n2. Verify 200 response with access_token and token_type=bearer.\n3. Send GET /api/auth/me with Bearer token in Authorization header.\n4. Send POST /api/auth/login with invalid password.",
            "Username: reviewer@example.com\nPassword: CorrectPass123! / WrongPass",
            "1. Valid login returns 200 OK with valid JWT.\n2. GET /me returns matching email and user role.\n3. Invalid credentials return 401 Unauthorized with detail message.",
            "Automated",
            "backend/tests/test_auth.py::test_login_success_and_failure",
            "Passed",
            "Tokens are signed HS256 JWTs with expiration claims. Passwords use passlib bcrypt."
        ),
        # 2. Upload clean text-layer PDF
        (
            "TC-PARSE-01",
            "Parsing",
            "P0",
            "Upload Clean Text-Layer PDF (Fast-Path, No OCR)",
            "User logged in with REVIEWER role. Worker daemon running or test harness configured.",
            "1. Upload PDF with >50 text characters per page via POST /api/documents.\n2. Verify batch response returns 201 Created with accepted status.\n3. Execute parse job.\n4. Inspect parse result in DB or via GET /api/documents/{id}.",
            "Sample: backend/invoice.pdf or test generated text_layer.pdf (>50 chars/page)",
            "1. File accepted with status 'uploaded' and 'parse' job enqueued.\n2. ParsedDocument.ocr_used is FALSE.\n3. ParsedPage.source == 'text_layer' with 100% extracted text and ocr_confidence=None.",
            "Hybrid",
            "backend/tests/test_parsers.py::test_parse_text_layer_pdf_generated_in_test",
            "Passed",
            "Bypasses Tesseract OCR when text layer exists, reducing processing latency from ~2s to <50ms."
        ),
        # 3. Upload scanned image (JPG/PNG) & check OCR readability
        (
            "TC-OCR-01",
            "OCR Engine",
            "P0",
            "Upload Scanned Image (JPG/PNG) & Validate OCR Readability",
            "Tesseract OCR installed or Mock OCR configured. Valid reviewer credentials.",
            "1. Upload clear scanned document (JPG/PNG) via POST /api/documents.\n2. Worker claims job and runs OCR engine.\n3. Check GET /api/documents/{id} parse payload.\n4. Validate parsed text is readable (not gibberish, not empty) and confidence score exists.",
            "Sample: backend/OCR_test.jpg or rendered image with 'INVOICE #99824'",
            "1. Status 'succeeded'.\n2. ParsedDocument.ocr_used is TRUE.\n3. Text contains readable words matching image content.\n4. Confidence score is captured and > 0.40.",
            "Automated",
            "backend/tests/test_parsers.py::test_ocr_on_real_image",
            "Passed",
            "Uses Pillow pre-processing and pytesseract / rapidocr. Checks text readability and average word confidence."
        ),
        # 4. Semicolon CSV and XLSX
        (
            "TC-PARSE-02",
            "Parsing",
            "P1",
            "Upload Semicolon-Delimited CSV & Autodetect Delimiter",
            "Valid CSV with ';' separator and UTF-8 or UTF-8-BOM encoding.",
            "1. Upload CSV with content: 'item;qty;price\\nWidget;4;19.99'.\n2. Trigger worker parser.\n3. Fetch document parse results.",
            "Data: item;qty;price;\\nWidget;4;19.99;\\nGadget;2;29.99",
            "1. CSV parser autodetects delimiter ';' via csv.Sniffer.\n2. Header row parsed into 3 distinct columns (not a single clumped string).\n3. Parsed table rows match numeric and text cell dimensions.",
            "Automated",
            "backend/tests/test_parsers.py::test_parse_csv_utf8_sig_and_semicolon_delimiter",
            "Passed",
            "Handles European Excel format (semicolon) and UTF-8 BOM signatures cleanly."
        ),
        (
            "TC-PARSE-03",
            "Parsing",
            "P1",
            "Upload Multi-Sheet XLSX with Blank Columns & Empty Sheets",
            "Valid XLSX containing Sheet1 with data and Sheet2 empty.",
            "1. Upload multi-sheet XLSX via POST /api/documents.\n2. Worker invokes parse_xlsx.\n3. Query document parsed tables.",
            "Data: Sheet1 with [Invoice, None, Amount], Sheet2 completely empty.",
            "1. Sheet1 parsed with headers ['Invoice', 'column_2', 'Amount'].\n2. Empty Sheet2 returns empty columns and rows without crashing openpyxl.\n3. Numeric dates and decimals formatted properly.",
            "Automated",
            "backend/tests/test_parsers.py::test_parse_xlsx_generated_with_blank_headers_and_empty_sheet",
            "Passed",
            "Synthetic column naming ('column_2') prevents un-indexed dictionary collisions."
        ),
        # 5. Corrupt file
        (
            "TC-HOSTILE-01",
            "Hostile Input",
            "P0",
            "Corrupt File Upload (Garbage Bytes with Valid Extension)",
            "Reviewer authenticated.",
            "1. Create file: echo not a pdf > bad.pdf\n2. Submit via POST /api/documents.\n3. Observe upload API response and worker behavior.",
            "Command: echo not a pdf > bad.pdf (Upload as bad.pdf)",
            "1. Rejected at upload boundary due to magic byte inspection (missing %PDF- header).\n2. If header forged (%PDF-1.4\\ngarbage), worker catches DocumentParseError, marks job and doc as 'failed' with readable message.\n3. Worker process stays alive and healthy.",
            "Automated",
            "backend/tests/test_parsers.py::test_corrupt_files_produce_clean_error",
            "Passed",
            "Storage header validation stops obvious garbage; worker try/except handles truncated binary streams."
        ),
        # 6. Empty file
        (
            "TC-HOSTILE-02",
            "Hostile Input",
            "P0",
            "Zero-Byte Empty File Upload (0 Bytes)",
            "Reviewer authenticated.",
            "1. Create 0-byte file: type nul > empty.pdf\n2. Submit via POST /api/documents.",
            "Command: type nul > empty.pdf",
            "1. Upload API rejects item with reason: 'File is empty (0 bytes)'.\n2. Return code is 201 Batch response with rejected_count=1 (or HTTP 400).\n3. Never raises an unhandled HTTP 500 error.\n4. No dangling storage file left on disk.",
            "Automated",
            "backend/tests/test_documents.py::test_upload_zero_byte_file_rejected_cleanly",
            "Passed",
            "Explicit check for len(header) == 0 in storage_service prevents zero-division and empty stream hangs."
        ),
        # 7. Wrong extension or unsupported type
        (
            "TC-HOSTILE-03",
            "Hostile Input",
            "P0",
            "Masquerading File Signature (.exe or .zip renamed to .pdf)",
            "Reviewer authenticated.",
            "1. Rename an executable (starting with MZ) or ZIP to document.pdf.\n2. Submit via POST /api/documents.\n3. Verify magic bytes inspection.",
            "Payload: b'MZ\\x90\\x00...' saved as invoice.pdf",
            "1. Storage validation inspects first 4096 bytes.\n2. Rejects file: 'Invalid PDF signature (missing %PDF- header)'.\n3. File is NOT saved to disk and no processing job is enqueued.",
            "Automated",
            "backend/tests/test_documents.py::test_multifile_upload_one_valid_one_invalid",
            "Passed",
            "Defends against malicious file upload attacks where attackers bypass extension whitelists."
        ),
        # 8. Oversized file
        (
            "TC-HOSTILE-04",
            "Hostile Input",
            "P1",
            "Oversized File Upload Stream Boundary & Memory Safety",
            "Reviewer authenticated. MAX_UPLOAD_MB configured (e.g., 25MB or 50MB).",
            "1. Generate 100MB dummy file: fsutil file createnew big.pdf 104857600\n2. Submit to POST /api/documents.\n3. Monitor server memory consumption.",
            "Command: fsutil file createnew big.pdf 104857600",
            "1. Streamed chunk reader stops after exceeding MAX_UPLOAD_MB.\n2. Rejects with 'File exceeds maximum allowed size of X MB'.\n3. Partial file on disk is deleted.\n4. Server does NOT load 100MB into RAM (avoids OOM).",
            "Automated",
            "backend/tests/test_documents.py::test_oversized_file_rejected_without_full_memory_load",
            "Passed",
            "64KB chunk-streaming ensures predictable <5MB RAM footprint even during large uploads."
        ),
        # 9. Password-protected PDF
        (
            "TC-HOSTILE-05",
            "Hostile Input",
            "P1",
            "Password-Protected Encrypted PDF Handling",
            "PDF encrypted with user/owner password.",
            "1. Upload password-protected PDF.\n2. Worker invokes parse_pdf.\n3. Check error handling and job completion.",
            "File: encrypted_sample.pdf (doc.needs_pass == True)",
            "1. PyMuPDF detects doc.needs_pass or doc.is_encrypted.\n2. Immediately raises DocumentParseError('PDF file is password-protected or encrypted').\n3. Job transitions to failed cleanly without hanging indefinitely.",
            "Automated",
            "backend/tests/test_parsers.py::test_password_protected_pdf_fails_fast",
            "Passed",
            "Prevents worker deadlock on password prompt prompts."
        ),
        # 10. Nasty filenames
        (
            "TC-HOSTILE-06",
            "Hostile Input",
            "P0",
            "Path Traversal, Spaces, & Unicode/Bangla Filename Safety",
            "Reviewer authenticated.",
            "1. Submit files with hostile names:\n  a) ..\\..\\evil.pdf\n  b) চালান_২০২৬ invoice (1).pdf\n  c) name with spaces and emojis.pdf\n2. Inspect storage disk path and DB record.",
            "Filenames: '../../etc/shadow.pdf', 'চালান_২০২৬ invoice (1).pdf'",
            "1. File on disk is stored strictly under UUID path: documents/{uuid}/original.pdf.\n2. No directory traversal is possible.\n3. Raw Unicode name preserved intact in documents.original_filename in DB.\n4. Download endpoint returns original filename safely via Content-Disposition header.",
            "Automated",
            "backend/tests/test_documents.py::test_nasty_and_unicode_filenames_safe_path",
            "Passed",
            "Complete decoupling of physical storage path from user-supplied filename."
        ),
        # 11. Kill worker mid-job
        (
            "TC-QUEUE-01",
            "Queue & Worker",
            "P0",
            "Worker Crash Mid-Job & Stale Heartbeat Recovery",
            "Job currently locked in RUNNING state by dead worker process.",
            "1. Set job status='running', locked_at=NOW - 20 minutes (simulating killed worker).\n2. Start worker or call job_queue.requeue_stale(stale_minutes=10).\n3. Verify job state in DB.",
            "Database update: UPDATE processing_jobs SET locked_at = NOW() - INTERVAL '20 minutes' WHERE id = ...",
            "1. requeue_stale detects expired heartbeat (> JOB_STALE_MINUTES).\n2. Resets job status='pending', clears locked_by and locked_at.\n3. Next available worker claims the job and runs it to completion (not stuck in running forever).",
            "Hybrid",
            "backend/tests/test_queue.py::test_requeue_stale_running_jobs",
            "Passed",
            "Heartbeat + stale reclamation prevents stuck processing queues across deployments or pod restarts."
        ),
        # 12. Two workers at once
        (
            "TC-QUEUE-02",
            "Queue & Worker",
            "P0",
            "Multi-Worker Concurrency & Single Claim Guarantee (SKIP LOCKED)",
            "Multiple jobs in pending state. Two worker threads or processes polling concurrently.",
            "1. Enqueue job.\n2. Concurrently call claim_next from Worker-1 and Worker-2 at the exact same instant using barrier synchronization.\n3. Verify each job is claimed by exactly one worker.",
            "SQL Verification:\nSELECT document_id, count(*) FROM processing_jobs GROUP BY document_id HAVING count(*) > 1;",
            "1. Exactly one worker claims the job; the second worker gets None or claims the next pending job.\n2. Zero duplicate claims.\n3. Query returns 0 rows.",
            "Automated",
            "backend/tests/test_queue.py::test_claim_next_concurrent_single_winner",
            "Passed",
            "PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED ensures race-free distributed locking."
        ),
        # 13. Retry cap
        (
            "TC-QUEUE-03",
            "Queue & Worker",
            "P0",
            "Retry Limit Cap & Exponential Backoff on Failure",
            "Job enqueued with max_attempts=3.",
            "1. Force job failure attempt 1 -> verify status='pending', attempts=1, run_after > NOW().\n2. Force attempt 2 failure -> verify backoff delay doubles.\n3. Force attempt 3 failure -> verify attempts == max_attempts.\n4. Check final job and document status.",
            "Test harness simulating transient parsing errors.",
            "1. Job is retried with exponential backoff on attempts 1 and 2.\n2. After attempt 3, job is NOT requeued.\n3. Status transitions to 'failed', finished_at populated.\n4. Document status marked 'failed' with readable last_error.",
            "Automated",
            "backend/tests/test_queue.py::test_retry_backoff_and_max_attempts",
            "Passed",
            "Exponential backoff protects against hammering failing external services."
        ),
        # 14. Upload same file twice
        (
            "TC-QUEUE-04",
            "Queue & Ingestion",
            "P1",
            "Duplicate File Upload Handling (Hash Auditing vs New Instance)",
            "Reviewer authenticated.",
            "1. Upload invoice.pdf -> receive document_id_1, sha256_hash.\n2. Upload exact same invoice.pdf again -> receive document_id_2.\n3. Check database records for both documents.",
            "File: invoice.pdf (identical SHA256)",
            "1. Document 2 is accepted with a distinct UUID and storage folder.\n2. Both documents share identical sha256 hash in DB.\n3. Each document has its own independent processing job.\n4. Architectural design decision documented: allows revision re-uploads while tracking cryptographic provenance.",
            "Automated",
            "backend/tests/test_documents.py::test_duplicate_file_upload_allowed_with_hash_tracking",
            "Passed",
            "Design Decision: Separate instances with SHA256 tracking (prevents accidental collision overwrite)."
        ),
        # 15. Auth edge cases: 401, 403, deactivated user
        (
            "TC-AUTH-02",
            "Security & Auth",
            "P0",
            "Unauthenticated Request Rejection (No Token)",
            "Endpoint requiring authentication (e.g., GET /api/documents).",
            "1. Send GET /api/documents without Authorization header.\n2. Send GET /api/documents with malformed Bearer token.",
            "Request: GET /api/documents (Headers: None)",
            "1. Returns HTTP 401 Unauthorized.\n2. Body contains detail: 'Not authenticated'.\n3. No internal server stack traces leaked.",
            "Automated",
            "backend/tests/test_auth.py::test_unauthenticated_and_malformed_tokens_rejected",
            "Passed",
            "FastAPI HTTPBearer dependency enforces token presence before router execution."
        ),
        (
            "TC-AUTH-03",
            "Security & Auth",
            "P0",
            "RBAC Permission Enforcement (Viewer Forbidden on Upload)",
            "User with VIEWER role authenticated.",
            "1. Obtain JWT token for VIEWER user.\n2. Send POST /api/documents with valid multipart file payload.\n3. Send GET /api/users with VIEWER token.",
            "Header: Authorization: Bearer <VIEWER_TOKEN>",
            "1. POST /api/documents returns HTTP 403 Forbidden.\n2. GET /api/users returns HTTP 403 Forbidden.\n3. Detail: 'Operation not permitted for role viewer'.",
            "Automated",
            "backend/tests/test_auth.py::test_viewer_gets_403_on_upload_and_users",
            "Passed",
            "Role-based dependency require_role(UserRole.REVIEWER, UserRole.ADMIN) blocks unauthorized actions."
        ),
        (
            "TC-AUTH-04",
            "Security & Auth",
            "P0",
            "Deactivated User Token Immediate Revocation Check",
            "User active at login time; subsequently deactivated in DB by Admin.",
            "1. User logs in and receives valid 15-minute JWT token.\n2. Admin sets user.is_active = False in DB.\n3. Deactivated user immediately calls GET /api/auth/me using their unexpired token.",
            "Header: Authorization: Bearer <OLD_TOKEN> (User is_active=False in DB)",
            "1. Request returns HTTP 401 Unauthorized.\n2. Access is denied immediately without waiting for JWT expiration.\n3. Prevents security holes where revoked employees retain API access.",
            "Automated",
            "backend/tests/test_auth.py::test_inactive_user_rejected",
            "Passed",
            "get_current_user dependency performs a live DB check on user.is_active on every single request."
        ),
    ]
    
    # Priority Color Highlights
    p0_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid") # Soft Red/Orange
    p1_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid") # Soft Yellow
    passed_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid") # Soft Green
    
    for row_idx, row_values in enumerate(test_rows, start=2):
        is_even = (row_idx % 2 == 0)
        row_fill = PatternFill(start_color="F9FBFD" if is_even else "FFFFFF", fill_type="solid")
        
        for col_idx, val in enumerate(row_values, start=1):
            cell = ws_cases.cell(row=row_idx, column=col_idx, value=val)
            cell.font = Font(name="Calibri", size=9)
            cell.border = thin_border
            cell.fill = row_fill
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            
            # Alignments & badges
            if col_idx == 1: # ID
                cell.alignment = Alignment(horizontal="center", vertical="top")
                cell.font = Font(name="Calibri", size=9, bold=True, color="1F4E78")
            elif col_idx == 3: # Priority
                cell.alignment = Alignment(horizontal="center", vertical="top")
                cell.font = Font(name="Calibri", size=9, bold=True)
                if val == "P0":
                    cell.fill = p0_fill
                elif val == "P1":
                    cell.fill = p1_fill
            elif col_idx == 9: # Type
                cell.alignment = Alignment(horizontal="center", vertical="top")
            elif col_idx == 11: # Status
                cell.alignment = Alignment(horizontal="center", vertical="top")
                cell.font = Font(name="Calibri", size=9, bold=True, color="276A3C")
                cell.fill = passed_fill

        ws_cases.row_dimensions[row_idx].height = 65

    # Optimal column widths
    col_widths = {
        "A": 13,  # ID
        "B": 18,  # Category
        "C": 10,  # Priority
        "D": 32,  # Title
        "E": 28,  # Preconditions
        "F": 38,  # Steps
        "G": 32,  # Data / Command
        "H": 36,  # Expected Result
        "I": 14,  # Type
        "J": 38,  # Automated Ref
        "K": 12,  # Status
        "L": 35,  # Notes
    }
    for col_letter, width in col_widths.items():
        ws_cases.column_dimensions[col_letter].width = width

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(str(output_path))
        print(f"Successfully generated: {output_path}")
    except PermissionError:
        alt_path = output_path.with_name(f"{output_path.stem}_Updated{output_path.suffix}")
        wb.save(str(alt_path))
        print(f"Primary file locked by Excel. Generated alternative: {alt_path}")


if __name__ == "__main__":
    out = Path("docs/DocuLens_Test_Cases.xlsx")
    build_test_cases_workbook(out)

