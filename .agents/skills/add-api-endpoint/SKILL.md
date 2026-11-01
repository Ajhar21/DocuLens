---
name: add-api-endpoint
description: Use when adding or changing a REST endpoint in the DocuLens FastAPI backend. Enforces router -> service -> repository layering, response envelope, permission dependency, and regenerating frontend types.
---

# Add an API endpoint

1. Find the matching row in PRD section 6. Use that exact method and path. If it is not listed, ask before adding.
2. Pydantic request/response schemas go in the module's `schemas.py`, not the router.
3. Business logic goes in `modules/<module>/service.py`. SQL goes in `db/repositories/`. Add the repository method first.
4. Router in `api/v1/<module>.py` does only: parse input -> call service -> return the envelope from `core/responses.py`.
5. Add `Depends(require_permission(Permission.<X>))` even while `RBAC_ENFORCEMENT=false`. Add the `Permission` to the enum and `ROLE_PERMISSIONS` per PRD 3.5 if new.
6. For anything touching documents, scope queries with `core.visibility`.
7. Sensitive actions (correct, approve, reject, retry, user changes) call `AuditService.record(...)`.
8. Map domain errors to 401/403/404/409/422 via `core/errors.py`. No bare `HTTPException` in services.
9. Heavy work (OCR, LLM, embeddings, spreadsheet parsing) is never done here. Enqueue a job instead.
10. Tests: add an API test with httpx covering success, 401, validation error, and (once enforcement is on) 403.
11. Frontend: run `npm run gen:api` from `frontend` and use the generated types.

Verify: `python -m pytest -q` from `backend`.
