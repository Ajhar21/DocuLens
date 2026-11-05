# DocuLens Day 3 — Frontend Architectural & Implementation Notes

## 1. Route Table & Endpoint Mapping

| Route | Screen / Component | Permitted Roles | Required Permission | Backend Endpoints Used | Description |
|---|---|---|---|---|---|
| `/review` | `ReviewQueuePage` | All Active Roles | `extraction:view` | `GET /api/v1/reviews` | Human review queue with review status filtering, validation issue badges, and pagination. |
| `/review/:documentId` | `ReviewDetailPage` | All Active Roles (View)<br>`EXEC`, `MGR`, `ADMIN` (Edit)<br>`MGR`, `ADMIN` (Approve/Reject) | `extraction:view` (View)<br>`extraction:edit` (Correct)<br>`correction:approve` (Sign-off) | `GET /api/v1/reviews/{id}`<br>`GET /api/v1/documents/{id}/file`<br>`PATCH /api/v1/reviews/{id}/corrections`<br>`POST /api/v1/reviews/{id}/approve`<br>`POST /api/v1/reviews/{id}/reject` | Two-pane review workspace: left document preview (Blob URL with iframe/image/download), right header correction form (dirty-field only submission, money string safety, original LLM diffs), read-only line items, and audit history. |
| `/reconciliation` | `ReconciliationListPage` | All Active Roles | `reconciliation:view` | `GET /api/v1/reconciliations` | Paginated list of reconciliation jobs with type and status filtering, discrepancy counts, and direct links to result reports. |
| `/reconciliation/new` | `ReconciliationNewPage` | All Active Roles | `reconciliation:run` | `GET /api/v1/documents` (Candidates)<br>`GET /api/v1/documents/{id}` (Detail & Tables)<br>`GET /api/v1/reconciliations/excel/{id}/sheets`<br>`POST /api/v1/reconciliations/pdf-pdf`<br>`POST /api/v1/reconciliations/pdf-excel` | New reconciliation runner: Tab 1 (PDF-to-PDF cross-document comparison with duplicate prevention); Tab 2 (PDF-to-Excel worksheet reconciliation with interactive column mapping, auto-suggestions, and sheet row identification). |
| `/reconciliation/:id` | `ReconciliationDetailPage` | All Active Roles | `reconciliation:view` | `GET /api/v1/reconciliations/{id}` | Shareable reconciliation comparison report: side-by-side header field table with tolerance diffs, visually prominent mismatch highlighting, line items section, and document cross-links. |
| `/search` | `SearchPage` | All Active Roles | `search:use` | `GET /api/v1/search` | Document search with shareable URL query state, debounced input, mode selector (hybrid/keyword/semantic), backend metadata filters, safe `<mark>` snippet rendering, and collapsible fusion ranking scores. |

---

## 2. Permission Architecture (`GET /auth/me` Case 2)

### Inspection Finding
Inspecting `GET /api/v1/auth/me` (`app.api.auth.read_current_user` returning `UserRead`) revealed that the endpoint exposes only the user's role:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "Full Name",
  "role": "FINANCE_EXECUTIVE",
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```
It does **not** expose a `permissions` array.

### Implementation Architecture
Per task specifications, **Case 2** was implemented:
1. Created a single module `src/lib/permissions.ts` mirroring the canonical `ROLE_PERMISSIONS` map from `backend/app/core/permissions.py`.
2. Explicit header disclaimer:
   > *"UI hints only; backend is the authority. UI gating is a user-experience convenience only. Every API request and mutation is independently and authoritatively authorized on the server."*
3. Components **never** branch on raw role names (e.g. `if (role === "admin")`). Components strictly use `usePermissions().can("permission:name")`.
4. Unit test suite `src/lib/__tests__/permissions.test.ts` validates that all canonical roles and declared permissions are present and adhere to the RBAC matrix (guards typos).

### Day 4 Follow-Up Recommendation (Drift Risk Mitigation)
- **Drift Risk**: If backend role permissions are modified in `backend/app/core/permissions.py`, `src/lib/permissions.ts` requires manual updating.
- **Proposed Enhancement**: In Day 4 backend refinement, update `UserRead` schema to include `permissions: list[str] = Field(default_factory=list)` populated dynamically from `ROLE_PERMISSIONS[user.role_name]`. The frontend hook can then read server-provided permissions directly.

---

## 3. Discovered Backend Deviations & Known PRD Gaps

| # | Dimension | PRD v1.1 Specification | Backend Implementation | Frontend Resolution & Classification |
|---|---|---|---|---|
| 1 | **Reconciliation Endpoint Plurality** | `/api/v1/reconciliation` (singular) | `/api/v1/reconciliations` (plural) | **Backend Departure**: Frontend calls canonical `/reconciliations`. |
| 2 | **Reconciliation Match Status Values** | `MATCH`, `MISMATCH`, `NOT_COMPARABLE` | `EXACT_MATCH`, `TOLERANCE_MATCH`, `MISMATCH`, `MISSING_IN_A`, `MISSING_IN_B`, `NOT_COMPARABLE` | **Backend Enhancement**: Frontend generates types directly from OpenAPI and styles each granular match status. |
| 3 | **Reconciliation Overall Status Values** | `MATCHED`, `MISMATCH_FOUND`, `PARTIALLY_MATCHED` | `MATCHED`, `MISMATCHED`, `ERROR` | **Backend Departure**: Handled via generated OpenAPI union type. |
| 4 | **Review Status String Casing** | UPPERCASE (`PENDING`, `APPROVED`, etc.) | lowercase (`pending`, `needs_review`, `in_review`, `corrected`, `approved`, `rejected`, `not_required`) | **Backend Departure**: Handled via generated OpenAPI union type. |
| 5 | **Search Query Obligation** | Filter-only search allowed without query string (FR-069) | `q` query string is strictly required (`min_length=1`) | **Known PRD Gap**: Backend returns HTTP 422 if `q` is absent. Frontend prevents submission without `q` and presents an explicit empty state linking to the Document List page for filter-only browsing. |
| 6 | **Unsupported Search Filters** | `reconciliation_status`, `document_type`, upload date range (FR-069) | Not present in `GET /api/v1/search` parameters | **Known PRD Gap**: Frontend does not fake these client-side and only exposes backend-supported filters (`supplier_name`, `date_from`, `date_to`, `amount_min`, `amount_max`, `review_status`). |
| 7 | **PDF-to-Excel Column Mapping** | Explicit interactive column mapping (FR-053) | Original: no `column_mapping` parameter on `ReconcilePdfExcelRequest`. | **Resolved via Narrow Backend Extension**: Added optional `column_mapping` dict, 422 header validation, required `invoice_number`, row identification in sheet, and metadata storage. Tested with 7 backend test suites. UI delivered in Tab 2. |
| 8 | **Line-Item Review Editing** | Vague mention in review screen | Scoped strictly to 8 invoice header fields | **Intentional Scope Limit**: Line items displayed read-only; header fields editable. |

---

## 4. Security & Safety Implementations

### XSS-Proof Snippet Rendering (`renderSnippet`)
- Backend `GET /search` generates highlighted snippets using PostgreSQL `ts_headline` with `<mark>` tags, surrounded by untrusted OCR/extracted document text.
- `src/features/search/snippet.tsx` completely eschews `dangerouslySetInnerHTML`.
- It tokenizes text on `<mark>` and `</mark>` tags using a pure parser:
  - Tokens inside `<mark>` tags render as `<mark className="rounded bg-amber-200 ...">` React elements.
  - All remaining text (including any embedded HTML, script tags, or onerror attributes) is rendered as plain React text strings which React escapes into HTML entities.
- Unit tested against malicious payloads:
  - `<script>alert('xss')</script>`: script tag is neutralized and printed as literal text; no script element exists in DOM.
  - `<img src=x onerror=alert(1)>`: img tag is neutralized; no image element exists in DOM.
  - Malformed/unbalanced `<mark>` tags handled gracefully without exceptions.

### Money String Handling
- In financial applications, JavaScript `Number` / IEEE 754 floating-point introduces rounding errors (e.g. `0.1 + 0.2 !== 0.3`).
- All money fields (`subtotal`, `tax`, `total`) are handled as strings end-to-end.
- Form inputs never call `parseFloat` or `Number()`.
- `buildDirtyCorrections` trims whitespace and compares string representations.
- Submissions send only fields that were actually modified by the reviewer.

### Column Mapping Auto-Suggestion
- `autoSuggestColumnMapping(sheetColumns)` is implemented as a pure functional helper in `src/features/reconciliation/auto-suggest.ts`.
- Uses normalized alias dictionaries to recognize accounting headers (e.g. "Doc Ref" -> `invoice_number`, "Vendor Title" -> `supplier_name`, "Gross Total" -> `total`, "Curr" -> `currency`).
- Prevents greedy duplicate assignments and leaves unmatched fields unmapped.

---

## 5. Automated Verification Results

All verification commands executed directly in the project environment:

### 1. Frontend Unit Tests (`npm test` via Vitest)
```
 ✓ src/features/review/__tests__/money-string.test.ts (5 tests)
 ✓ src/features/reconciliation/__tests__/auto-suggest.test.ts (5 tests)
 ✓ src/lib/__tests__/permissions.test.ts (4 tests)
 ✓ src/features/search/__tests__/snippet.test.tsx (7 tests)

 Test Files  4 passed (4)
      Tests  21 passed (21)
   Duration  9.29s
```

### 2. Frontend TypeScript Compilation (`npm run typecheck`)
```
> doculens-frontend@0.1.0 typecheck
> tsc -b --noEmit

(Exited with code 0 - Zero errors)
```

### 3. Frontend Code Quality & ESLint (`npm run lint`)
```
> doculens-frontend@0.1.0 lint
> eslint . --max-warnings 0

(Exited with code 0 - Zero errors, Zero warnings)
```

### 4. Frontend Production Build (`npm run build`)
```
> doculens-frontend@0.1.0 build
> tsc -b && vite build

vite v6.4.5 building for production...
✓ 1795 modules transformed.
dist/index.html                   1.04 kB │ gzip:  0.50 kB
dist/assets/index-MHU5NYq4.css   42.06 kB │ gzip:  8.35 kB
dist/assets/query-B6zEF_ma.js    49.43 kB │ gzip: 15.17 kB
dist/assets/radix-CJke_hEb.js   105.14 kB │ gzip: 35.28 kB
dist/assets/react-DgpQvGIS.js   158.17 kB │ gzip: 51.88 kB
dist/assets/index-F984U7NJ.js   339.57 kB │ gzip: 87.26 kB
✓ built in 7.40s
```

### 5. Backend Reconciliation Tests (`pytest tests/test_reconciliation.py`)
```
tests\test_reconciliation.py .......                                     [100%]
======================= 7 passed, 2 warnings in 36.41s ========================
```
Covering:
- `test_reconcile_pdf_pdf_matched_pair`
- `test_reconcile_pdf_pdf_mismatched_pair`
- `test_reconcile_pdf_excel_with_sheet_selection` (omitted mapping preserves backward compatibility)
- `test_reconciliation_precondition_validations`
- `test_reconciliation_list_and_get_details`
- `test_reconcile_pdf_excel_with_column_mapping_success` (explicit mapping and multi-row matching)
- `test_reconcile_pdf_excel_mapping_validations` (422 for missing invoice_number, unknown header, ambiguous record, and record not found)
