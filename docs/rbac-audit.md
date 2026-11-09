# DocuLens RBAC & User Management Audit (Phase 0)

**Date:** 2026-11-09  
**Scope:** Backend (`backend/app/`) and Frontend (`frontend/src/`) authentication, authorization, user lifecycle, admin bootstrap, and audit logging.

---

## 1. How Authentication Works Today

### Token Architecture
DocuLens uses a dual-token architecture combining short-lived JWT access tokens with database-backed rotating refresh tokens:
- **Access Token (JWT):**
  - **Algorithm:** `HS256` signed with `settings.JWT_SECRET`.
  - **Claims:** `sub` (stringified `user.id` UUID), `role` (`user.role_name`), `iat` (UTC issued-at), `exp` (UTC expiry, default `60` minutes via `settings.JWT_EXPIRE_MINUTES`).
  - **Issued & Verified in:** [`backend/app/core/security.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/security.py) (`create_access_token`, `decode_access_token`).
  - **Limitation Today:** Does **not** embed a `tv` (`token_version`) claim; while `get_current_user` checks `user.is_active` in the database on every request, role changes or password changes do not invalidate already-issued access tokens until their 60-minute `exp` elapses.
- **Refresh Token (Stateful DB Rotation):**
  - **Generation & Hashing:** 32-byte cryptographically random URL-safe token (`secrets.token_urlsafe(32)`), hashed with `SHA-256` (`hash_refresh_token` in [`backend/app/core/security.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/security.py)). Only `token_hash` is persisted in the `refresh_tokens` table.
  - **Rotation & Replay Detection:** Managed in [`backend/app/services/user_service.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/services/user_service.py) (`refresh_access_token`). Each refresh rotates the token within a `family_id`; replaying a previously revoked token revokes the entire token family immediately (`401 refresh_token_reused`).

### Password Hashing
- **Algorithm:** Argon2id via `argon2-cffi` (`PasswordHasher()` in [`backend/app/core/security.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/security.py)).
- **Functions:** `hash_password(password)` and `verify_password(plain_password, hashed_password)` (catches `VerifyMismatchError`, `VerificationError`, `InvalidHashError`).

### Per-Request Current User Resolution
- Resolved in [`backend/app/core/deps.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/deps.py) via `get_current_user`:
  1. Extracts the Bearer token via `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")`.
  2. Decodes JWT and parses `sub` as `uuid.UUID`.
  3. Queries `SELECT ... FROM users JOIN roles ... WHERE users.id = :user_id` on every request.
  4. Rejects with `401 Unauthorized` if `user is None` or `not user.is_active`.
  5. **Gap:** Does not verify `token_version` against the JWT payload, and does not enforce a `must_change_password` gate.

---

## 2. Role Storage & Canonical Role Names

### Storage Mechanism
- Stored in a normalized `roles` table (created in migration [`0003_day3_rbac_and_audit_logs.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/alembic/versions/0003_day3_rbac_and_audit_logs.py)) with columns:
  - `id` (`UUID PRIMARY KEY DEFAULT gen_random_uuid()`)
  - `name` (`VARCHAR(50) UNIQUE NOT NULL`) constrained by `CHECK (name IN ('FINANCE_EXECUTIVE', 'FINANCE_MANAGER', 'ACCOUNTS_AUDIT', 'SYSTEM_ADMIN'))`
  - `description` (`TEXT NULL`)
- Each user row in `users` has a non-nullable foreign key `role_id UUID NOT NULL REFERENCES roles(id)` indexed by `ix_users_role_id`, eager-loaded via `lazy="joined"` on `User.role_rel`.

### Exact Role Names in Use
Defined in `RoleName(str, enum.Enum)` in [`backend/app/models/user.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/models/user.py):
1. `FINANCE_EXECUTIVE`
2. `FINANCE_MANAGER`
3. `ACCOUNTS_AUDIT`
4. `SYSTEM_ADMIN`

---

## 3. Authorization Verification Matrix

### Central Permission Map vs. Direct Role Checks
- **Backend:** Uses a central declarative map `ROLE_PERMISSIONS: dict[str, frozenset[Permission]]` in [`backend/app/core/permissions.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/permissions.py) and a single FastAPI dependency factory `require_permission(Permission.X)`. Zero route handlers check role names directly.
- **Permission Denial & Unauthenticated Status Codes:**
  - Unauthenticated requests (missing/invalid/expired JWT or inactive user) return **`401 Unauthorized`** (`error.code = "unauthorized"`).
  - Insufficient permission returns **`403 Forbidden`** (`error.code = "forbidden"`, message `"Insufficient permissions: '<perm>' required"`).
- **System Admin Least-Privilege Note:**
  - In [`backend/app/core/permissions.py:L67`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/permissions.py#L67), `_SYSTEM_ADMIN_PERMS = frozenset(Permission)`, meaning `SYSTEM_ADMIN` holds all permissions (including `extraction:edit`, `correction:approve`, `reconciliation:run`).
  - While PRD Section 3 primarily describes `SYSTEM_ADMIN` around user/role administration, job monitoring/retry, system config, and audit logs, the existing Day 3 test suite ([`backend/tests/test_rbac_matrix.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/tests/test_rbac_matrix.py)) explicitly asserts `200`/`201`/`202` for `SYSTEM_ADMIN` across all 27 endpoints. Removing permissions from `SYSTEM_ADMIN` would break the existing 111-test suite; therefore, this is flagged as an intentional design choice preserved for backward compatibility.

### Complete Route Authorization Table

*(Note: All routes are mounted under `/api/v1/*` with non-schema backward-compatible aliases under `/api/*`.)*

| Endpoint | Method | Current Guard (`backend/app/api/`) | Effective Permitted Roles Today | Expected per PRD Section 3 | Verdict |
|---|---|---|---|---|---|
| `/api/v1/health` | `GET` | Public (`None`) | Public / Any | Public health check | **CORRECT** |
| `/api/v1/auth/login` | `POST` | Public (`None`) | Public | Public authentication | **CORRECT** |
| `/api/v1/auth/refresh` | `POST` | Public (`None`, validates refresh token) | Valid refresh token holder | Public token refresh | **CORRECT** |
| `/api/v1/auth/logout` | `POST` | `Depends(get_current_user)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated users | **CORRECT** |
| `/api/v1/auth/me` | `GET` | `Depends(get_current_user)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated users | **CORRECT** |
| `/api/v1/users` | `GET` | `require_permission(USER_MANAGE)` | `SYSTEM_ADMIN` | `SYSTEM_ADMIN` | **CORRECT** |
| `/api/v1/users` | `POST` | `require_permission(USER_MANAGE)` | `SYSTEM_ADMIN` | `SYSTEM_ADMIN` | **CORRECT** |
| `/api/v1/users/{user_id}` | `GET` | `require_permission(USER_MANAGE)` (router) | `SYSTEM_ADMIN` | `SYSTEM_ADMIN` | **CORRECT** |
| `/api/v1/users/{user_id}` | `PATCH` | `require_permission(USER_MANAGE)` | `SYSTEM_ADMIN` | `SYSTEM_ADMIN` | **CORRECT** |
| `/api/v1/users/{user_id}/role` | `PATCH` | `require_permission(USER_MANAGE)` | `SYSTEM_ADMIN` | `SYSTEM_ADMIN` | **CORRECT** |
| `/api/v1/users/{user_id}/status` | `PATCH` | `require_permission(USER_MANAGE)` | `SYSTEM_ADMIN` | `SYSTEM_ADMIN` | **CORRECT** |
| `/api/v1/documents` | `POST` | `require_permission(DOCUMENT_UPLOAD)` | `EXEC`, `MGR`, `ADMIN` (`AUDIT` -> 403) | `EXEC`, `MGR`, `ADMIN` (Audit denied) | **CORRECT** |
| `/api/v1/documents/upload` | `POST` | `require_permission(DOCUMENT_UPLOAD)` | `EXEC`, `MGR`, `ADMIN` (`AUDIT` -> 403) | `EXEC`, `MGR`, `ADMIN` (Audit denied) | **CORRECT** |
| `/api/v1/documents/upload-policy` | `GET` | `require_permission(DOCUMENT_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/documents` | `GET` | `require_permission(DOCUMENT_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/documents/{document_id}` | `GET` | `require_permission(DOCUMENT_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles (includes per-doc job status) | **CORRECT** |
| `/api/v1/documents/{document_id}/status` | `GET` | `require_permission(DOCUMENT_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/documents/{document_id}/extraction` | `GET` | `require_permission(EXTRACTION_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/documents/{document_id}/validation` | `GET` | `require_permission(VALIDATION_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/documents/{document_id}/reprocess` | `POST` | `require_permission(DOCUMENT_UPLOAD)` | `EXEC`, `MGR`, `ADMIN` (`AUDIT` -> 403) | `EXEC`, `MGR`, `ADMIN` | **CORRECT** |
| `/api/v1/documents/{document_id}/file` | `GET` | `require_permission(DOCUMENT_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/documents/{document_id}/history` | `GET` | `require_permission(DOCUMENT_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles (document processing history) | **CORRECT** |
| `/api/v1/jobs` | `GET` | `require_permission(JOB_VIEW)` | `SYSTEM_ADMIN` (`EXEC`/`MGR`/`AUDIT` -> 403) | `SYSTEM_ADMIN` (global job queue; locked by `test_rbac_matrix.py`) | **CORRECT** |
| `/api/v1/jobs/{job_id}` | `GET` | `require_permission(JOB_VIEW)` | `SYSTEM_ADMIN` (`EXEC`/`MGR`/`AUDIT` -> 403) | `SYSTEM_ADMIN` (locked by `test_rbac_matrix.py`) | **CORRECT** |
| `/api/v1/jobs/{job_id}/retry` | `POST` | `require_permission(JOB_RETRY)` | `SYSTEM_ADMIN` (`EXEC`/`MGR`/`AUDIT` -> 403) | `SYSTEM_ADMIN` ("retry failed jobs" per PRD 3.4) | **CORRECT** |
| `/api/v1/reviews` | `GET` | `require_permission(DOCUMENT_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/reviews/{document_id}` | `GET` | `require_permission(DOCUMENT_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/reviews/{document_id}/corrections` | `PATCH` | `require_permission(EXTRACTION_EDIT)` | `EXEC`, `MGR`, `ADMIN` (`AUDIT` -> 403) | `EXEC`, `MGR`, `ADMIN` (Audit strictly denied) | **CORRECT** |
| `/api/v1/reviews/{document_id}/approve` | `POST` | `require_permission(CORRECTION_APPROVE)` | `MGR`, `ADMIN` (`EXEC`/`AUDIT` -> 403) | `MGR`, `ADMIN` (Executive & Audit strictly denied) | **CORRECT** |
| `/api/v1/reviews/{document_id}/reject` | `POST` | `require_permission(CORRECTION_APPROVE)` | `MGR`, `ADMIN` (`EXEC`/`AUDIT` -> 403) | `MGR`, `ADMIN` (Executive & Audit strictly denied) | **CORRECT** |
| `/api/v1/audit-logs` | `GET` | `require_permission(AUDIT_VIEW)` | `MGR`, `AUDIT`, `ADMIN` (`EXEC` -> 403) | `MGR`, `AUDIT`, `ADMIN` (Executive strictly denied) | **CORRECT** |
| `/api/v1/reconciliations/excel/{id}/sheets` | `GET` | `require_permission(RECONCILIATION_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/reconciliations/pdf-pdf` | `POST` | `require_permission(RECONCILIATION_RUN)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles (including Audit per PRD 3.3) | **CORRECT** |
| `/api/v1/reconciliations/pdf-excel` | `POST` | `require_permission(RECONCILIATION_RUN)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles (including Audit per PRD 3.3) | **CORRECT** |
| `/api/v1/reconciliations` | `GET` | `require_permission(RECONCILIATION_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/reconciliations/{id}` | `GET` | `require_permission(RECONCILIATION_VIEW)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| `/api/v1/search` | `GET` | `require_permission(SEARCH_USE)` | `EXEC`, `MGR`, `AUDIT`, `ADMIN` | All authenticated roles | **CORRECT** |
| *Export / System Config routes* | N/A | *Not implemented as separate routes* | N/A | Out of scope for MVP (file download is via `/documents/{id}/file`) | **N/A** |

### Specific Rule Verifications (with File & Line References)
1. **Audit Team (`ACCOUNTS_AUDIT`) restrictions & capabilities:**
   - Defined in [`backend/app/core/permissions.py:L55-L65`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/permissions.py#L55-L65): holds `DOCUMENT_VIEW`, `EXTRACTION_VIEW`, `VALIDATION_VIEW`, `RECONCILIATION_RUN`, `RECONCILIATION_VIEW`, `SEARCH_USE`, `AUDIT_VIEW`.
   - **Cannot** upload documents (`DOCUMENT_UPLOAD` absent -> `403`), **cannot** modify extracted data (`EXTRACTION_EDIT` absent -> `403` on `PATCH /reviews/{id}/corrections`), **cannot** approve/reject (`CORRECTION_APPROVE` absent -> `403`), **cannot** manage users (`USER_MANAGE` absent -> `403`).
   - **Can** run both PDF-to-PDF and PDF-to-Excel reconciliations (`RECONCILIATION_RUN` present). **Verdict: CORRECT.**
2. **Finance Executive (`FINANCE_EXECUTIVE`) restrictions & capabilities:**
   - Defined in [`backend/app/core/permissions.py:L35-L46`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/permissions.py#L35-L46): holds `DOCUMENT_UPLOAD`, `DOCUMENT_VIEW`, `EXTRACTION_VIEW`, `VALIDATION_VIEW`, `EXTRACTION_EDIT`, `RECONCILIATION_RUN`, `RECONCILIATION_VIEW`, `SEARCH_USE`.
   - **Can** upload, apply header corrections (immediately sets `review_status = "corrected"` in [`backend/app/services/review_service.py:L290`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/services/review_service.py#L290)), and run reconciliation.
   - **Cannot** approve/reject (`CORRECTION_APPROVE` absent -> `403`), **cannot** view global audit logs (`AUDIT_VIEW` absent -> `403`), **cannot** manage users (`USER_MANAGE` absent -> `403`). **Verdict: CORRECT.**
3. **Finance Manager (`FINANCE_MANAGER`) capabilities:**
   - Defined in [`backend/app/core/permissions.py:L48-L53`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/permissions.py#L48-L53): `_FINANCE_EXECUTIVE_PERMS | {CORRECTION_APPROVE, AUDIT_VIEW}`.
   - Has all Executive permissions plus approve/reject and global audit log access. **Verdict: CORRECT.**
4. **Object-Level Rules:**
   - Single visibility rule in [`backend/app/core/visibility.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/core/visibility.py): `visible_documents_filter(user)` returns `sa.true()`, allowing all roles to view all documents.
   - Editing lock on `APPROVED` documents in [`backend/app/services/review_service.py:L220-L223`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/services/review_service.py#L220-L223): `if doc.review_status == "approved": raise ConflictError(...)` (`409 Conflict` for all roles, with `SELECT ... FOR UPDATE` row locking at line 215). **Verdict: CORRECT.**

### Frontend-Only Role Checks & Bugs Found
1. **Stale Legacy Role Check in [`frontend/src/features/auth/roles.ts`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/frontend/src/features/auth/roles.ts):**
   - `canUploadDocuments(role)` and `canReprocessDocuments(role)` check `role === "reviewer" || role === "admin"` (legacy Day 1 strings).
   - Used in [`frontend/src/features/documents/DocumentsPage.tsx:L11`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/frontend/src/features/documents/DocumentsPage.tsx#L11) and [`frontend/src/features/documents/detail/ProcessingCard.tsx:L71`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/frontend/src/features/documents/detail/ProcessingCard.tsx#L71).
   - Because canonical roles returned by the backend are `FINANCE_EXECUTIVE`, `FINANCE_MANAGER`, `ACCOUNTS_AUDIT`, and `SYSTEM_ADMIN`, **upload and reprocess buttons are hidden in the UI for every real user**!
   - **Fix required:** Replace with `usePermissions().can("document:upload")` (or update `roles.ts` to delegate to `ROLE_PERMISSIONS`).

---

## 4. Admin Seeding Audit

- **Location:** [`backend/app/seed.py`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/seed.py) (`seed_admin`), invoked at FastAPI startup in [`backend/app/main.py:L23-L48`](file:///d:/Agentic%20AI%20Engineer/Care%20Guide%20Interview%20Task/DocuLens/backend/app/main.py#L23-L48) (`_bootstrap_roles_and_admin`).
- **How It Works Today:**
  1. Ensures the 4 canonical roles exist in `roles` (`user_repo.ensure_roles_seeded(db)`).
  2. Looks up a user by `settings.ADMIN_EMAIL` (`user_repo.get_user_by_email(db, email)`).
  3. If no user has `ADMIN_EMAIL`, creates the user with `role = SYSTEM_ADMIN`, `is_active = True`, and Argon2-hashed `ADMIN_PASSWORD`.
  4. On normal boot (`reset_password=False`), it does **not** overwrite the password of an existing user.
- **Gaps & Risks Identified:**
  1. **Checks by email instead of checking if any `SYSTEM_ADMIN` exists:** If an admin changes the bootstrap admin's email or creates another `SYSTEM_ADMIN` and deactivates/demotes `ADMIN_EMAIL`, lines 63–74 in `seed.py` forcibly re-promote and re-activate `ADMIN_EMAIL` on every server restart!
  2. **Does not set `must_change_password=True`** when seeding a brand-new bootstrap admin. (Per Requirement H, existing seeded admins from earlier days must keep `must_change_password=False` so the current dev admin is not retroactively locked out, while newly seeded admins get `must_change_password=True`).
  3. **Missing CLI module `python -m app.create_admin`:** Only `python -m app.seed` exists today; `app/create_admin.py` accepting `--email` / `--password` args or interactive prompt is missing.

---

## 5. User Model Fields: Present vs. Needed

| Field | Present in `users` Today? | Current Type / Default | Phase 1 Requirement | Action Needed |
|---|---|---|---|---|
| `id` | Yes | `UUID PK DEFAULT gen_random_uuid()` | Keep | None |
| `email` | Yes | `VARCHAR(255) UNIQUE NOT NULL` | Keep | None |
| `full_name` | Yes | `VARCHAR(255) NOT NULL` | Keep (allow default/optional on invite, set on accept) | Keep column `NOT NULL` (default to email prefix or provided name on invite) |
| `password_hash` | Yes | `VARCHAR(255) NOT NULL` | Keep | On invite, store an unusable sentinel hash until invite is accepted |
| `role_id` | Yes | `UUID FK -> roles.id NOT NULL` | Keep | None |
| `is_active` | Yes | `BOOLEAN DEFAULT true NOT NULL` | Keep (`False` while `invited` or `deactivated`) | None |
| `created_at` | Yes | `TIMESTAMPTZ DEFAULT now() NOT NULL` | Keep | None |
| `updated_at` | Yes | `TIMESTAMPTZ DEFAULT now() NOT NULL` | Keep | None |
| `must_change_password` | **No** | Missing | `BOOLEAN DEFAULT false NOT NULL` | Add via Alembic migration `0007` |
| `token_version` | **No** | Missing | `INTEGER DEFAULT 0 NOT NULL` | Add via Alembic migration `0007` |
| `last_login_at` | **No** | Missing | `TIMESTAMPTZ NULL` | Add via Alembic migration `0007`; update on login & accept-invite |
| `invited_by` | **No** | Missing | `UUID FK -> users.id ON DELETE SET NULL NULL` | Add via Alembic migration `0007` |
| `deactivated_at` | **No** | Missing | Distinguish `invited` vs `deactivated` cleanly | Add `deactivated_at TIMESTAMPTZ NULL` (or derive from `user_action_tokens` / `last_login_at`) |
| `user_action_tokens` table | **No** | Missing | Store hashed single-use `INVITE` and `PASSWORD_RESET` tokens with expiry (`INVITE_TTL_HOURS`, default 72h), `used_at`, `revoked_at` | Create table `user_action_tokens` via Alembic migration `0007` |

---

## 6. Audit Log Audit

### Schema (`audit_logs`)
- `id`: `UUID PK`
- `user_id`: `UUID FK -> users.id ON DELETE SET NULL NULL` (Actor ID)
- `action`: `TEXT NOT NULL`
- `entity_type`: `TEXT NOT NULL`
- `entity_id`: `UUID NOT NULL` (Target Entity / Target User ID)
- `old_values`: `JSONB NULL`
- `new_values`: `JSONB NULL`
- `created_at`: `TIMESTAMPTZ DEFAULT now() NOT NULL`

### Events Written Today
- **User Events (`entity_type="USER"`):** `USER_CREATED`, `USER_UPDATED`, `USER_PASSWORD_CHANGED`, `USER_ROLE_CHANGED`, `USER_STATUS_CHANGED`.
- **Document & Review Events:** `DOCUMENT_UPLOADED`, `DOCUMENT_CORRECTED`, `DOCUMENT_APPROVED`, `DOCUMENT_REJECTED`.
- **Reconciliation & Job Events:** `reconciliation:run`, `JOB_RETRIED`.

### Gaps vs. Phase 1F Requirements
- Phase 1F requires dot-namespaced lifecycle audit events with `actor_id` (`user_id`), `target_user_id` (`entity_id` + `new_values.target_user_id`), and timestamp:
  - `user.invited`
  - `invite.accepted`
  - `invite.revoked`
  - `user.role_changed` (recording `old_values={"role": old}` -> `new_values={"role": new}`)
  - `user.deactivated`
  - `user.reactivated`
  - `password.changed`
  - `password.reset_requested`
  - Optional: `auth.login_failed`
- **Compatibility Note:** Existing test `test_rbac_matrix.py::test_audit_logs_recorded_for_user_changes_and_upload` checks `assert "USER_CREATED" in actions`, `assert "USER_ROLE_CHANGED" in actions`, and `assert "USER_STATUS_CHANGED" in actions`. We will record the new canonical dot-namespaced events (`user.role_changed`, `user.deactivated`, `user.reactivated`) and retain the legacy uppercase entries on the legacy `/users` mutations so both new and existing tests pass without modification.

---

## 7. Summary of Gaps vs. PRD Section 3 & Phase 1 Requirements

1. **Admin Bootstrap (`app/seed.py` & `app/create_admin.py`):**
   - Must check if *any* `SYSTEM_ADMIN` user exists before seeding from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
   - Must never overwrite existing users' roles/status/passwords on boot.
   - Must set `must_change_password=True` when creating a new admin via bootstrap/CLI (while leaving existing DB admins with `must_change_password=False`).
   - Need `python -m app.create_admin` CLI supporting `--email` / `--password` flags or interactive prompts.
2. **Forced Password Change Gate (`must_change_password`):**
   - When `current_user.must_change_password` is `True`, `get_current_user` (or route dependency) must block all protected routes except `POST /api/v1/auth/change-password`, `POST /api/v1/auth/logout`, and `GET /api/v1/auth/me` with `403 Forbidden` and `error.code = "PASSWORD_CHANGE_REQUIRED"`.
   - Need `POST /api/v1/auth/change-password` validating current password, enforcing min length 12 & not equal to previous password, clearing `must_change_password`, and incrementing `token_version`.
3. **Token Version & Immediate Session Revocation (`token_version`):**
   - Embed `tv: user.token_version` in access tokens.
   - Verify `payload.get("tv", 0) == user.token_version` and `user.is_active` in `get_current_user` on every request so deactivation, role changes, and password changes immediately invalidate existing JWTs (`401 Unauthorized`).
4. **Invite & Reset-Password Flow (No Temp Passwords):**
   - Need `POST /api/v1/admin/users/invite`, `POST /api/v1/admin/users/{id}/resend-invite`, `POST /api/v1/admin/users/{id}/revoke-invite`, `POST /api/v1/admin/users/{id}/reset-password`, and public `POST /api/v1/auth/accept-invite` + `POST /api/v1/auth/reset-password`.
   - Tokens must be cryptographically random, SHA-256 hashed in `user_action_tokens`, single-use, expiring after `INVITE_TTL_HOURS` (default 72h), returning the invite/reset URL in the API response for clipboard copy (since no SMTP provider is configured).
5. **Admin User Lifecycle Endpoints:**
   - Need `GET /api/v1/admin/users`, `PATCH /api/v1/admin/users/{id}/role`, `POST /api/v1/admin/users/{id}/deactivate`, `POST /api/v1/admin/users/{id}/reactivate` (while keeping `/api/v1/users/*` working for existing tests).
6. **Frontend Gaps:**
   - Fix `canUploadDocuments` and `canReprocessDocuments` in `frontend/src/features/auth/roles.ts` to use canonical permissions (`document:upload`) instead of legacy `"reviewer" | "admin"` strings.
   - Add `/change-password` page and automatic redirect in `ProtectedRoute` when `user.must_change_password === true`.
   - Add public `/accept-invite` page (handling invite acceptance and password reset tokens).
   - Add `/admin/users` page (`user:manage` gated) with user table (name, email, role, status: `invited` / `active` / `deactivated`, last login), Invite User dialog, copyable invite/reset link dialog, role selector, deactivate/reactivate, resend/revoke invite, and user audit trail section.

