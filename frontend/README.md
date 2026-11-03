# DocuLens — Frontend (Day 1)

Production-grade React 18 + TypeScript (strict) frontend for **DocuLens**, covering authentication, role-based access control, multi-file batch document ingestion with server-side validation diagnostics, and live status polling.

---

## Setup & Run Commands (`cmd.exe`)

```cmd
cd frontend
copy .env.example .env
npm install
npm run dev
```

 The Vite dev server starts at `http://localhost:5173` and proxies all `/api/*` requests to `http://127.0.0.1:8000` (configured via `BACKEND_URL`), eliminating dev-time CORS configuration.

### Quality & Production Build (`cmd.exe`)

```cmd
cd frontend
npm run lint
npm run typecheck
npm run build
npm run preview
```

---

## Environment Variables

| Variable | Default | Scope | Purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | `/api` | Browser (`import.meta.env`) | Base URL prefix used by the API client. Keep `/api` in development so requests traverse the Vite proxy. |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Vite dev server only | Target FastAPI origin for the `/api` dev proxy in `vite.config.ts`. Never bundled into browser assets. |

---

## Folder Structure

```text
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx        # Responsive desktop sidebar + mobile Sheet shell
│   │   │   ├── Sidebar.tsx          # Primary navigation (Documents)
│   │   │   └── TopBar.tsx           # Role badge, user avatar, account menu + logout
│   │   └── ui/                      # shadcn/ui (Radix primitives + Tailwind CSS v3)
│   ├── features/
│   │   ├── auth/
│   │   │   ├── api.ts               # POST /auth/login, GET /auth/me
│   │   │   ├── auth-context.ts      # AuthContext contract
│   │   │   ├── AuthProvider.tsx     # Session lifecycle, 401 listener, JWT exp timer
│   │   │   ├── login-schema.ts      # Zod login form schema
│   │   │   ├── LoginPage.tsx        # Split-layout login view with error classification
│   │   │   ├── ProtectedRoute.tsx   # Route guard + skeleton shell during session boot
│   │   │   ├── roles.ts             # RBAC permission helpers (admin/reviewer vs viewer)
│   │   │   └── use-auth.ts          # Typed hook for AuthContext
│   │   └── documents/
│   │       ├── api.ts               # GET /documents, GET /documents/upload-policy, POST /documents
│   │       ├── DocumentsPage.tsx    # Role-gated UploadPanel + DocumentTable
│   │       ├── DocumentTable.tsx    # Paginated, filterable table with live polling
│   │       ├── Dropzone.tsx         # Accessible keyboard + drag-and-drop file picker
│   │       ├── file-precheck.ts     # Client-side size/extension check against server policy
│   │       ├── queries.ts           # TanStack Query hooks + conditional refetchInterval
│   │       ├── status.ts            # Backend status presentation metadata
│   │       ├── StatusBadge.tsx      # Color + icon + label badge with error tooltip
│   │       └── UploadPanel.tsx      # Staged file list, upload progress, per-file results
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts            # Unified fetch wrapper + XHR progress uploader
│   │   │   ├── errors.ts            # Single normalized ApiError class
│   │   │   └── types.ts             # Single source of truth for API DTOs
│   │   ├── auth/
│   │   │   └── token-storage.ts     # Isolated localStorage JWT adapter
│   │   ├── config.ts                # Validated runtime config
│   │   ├── format.ts                # Tabular byte size, date-time, and initials formatters
│   │   └── utils.ts                 # Tailwind class merge helper (`cn`)
│   ├── App.tsx                      # Providers + React Router v6 route tree
│   ├── index.css                    # Light-theme CSS custom properties (shadcn/ui tokens)
│   └── main.tsx                     # Application entry point
├── .env.example
├── components.json
├── eslint.config.js
├── package.json
├── tailwind.config.ts
├── tsconfig.json
└── vite.config.ts
```

---

## Design Decisions & Trade-Offs

- **Isolated `localStorage` Token Adapter (`lib/auth/token-storage.ts`):** Storing JWTs in `localStorage` exposes the token if an XSS vulnerability occurs, whereas `httpOnly` cookies mitigate XSS token theft. Because the backend issues Bearer tokens in the JSON login body, we isolate all storage calls behind one module so migrating to `httpOnly` cookies later requires zero UI changes.
- **Unified API Client with `XMLHttpRequest` Upload Progress (`lib/api/client.ts`):** Standard `fetch` is used for all JSON/form requests, but browser `fetch` cannot report byte-level upload progress across browsers. A dedicated `uploadWithProgress` function inside the same client module uses `XMLHttpRequest` while sharing Bearer token injection, global `401` handling, and `ApiError` normalization.
- **Advisory Client Pre-Check with Server Authority (`features/documents/file-precheck.ts`):** The UI fetches `GET /api/documents/upload-policy` and flags unsupported extensions, `0`-byte files, or oversized files immediately in the staged list. Instead of silently dropping flagged files, users can either remove them or submit the batch so the server remains the single authority and returns its verbatim per-file rejection reason.
- **Batch Upload Status Semantics (`201` / `207` / `422`):** A batch upload returns `201 Created` when all files succeed, `207 Multi-Status` on partial acceptance, and `422 Unprocessable Entity` (`error.code = "all_files_rejected"`) when every file is rejected. The API client resolves the `BatchUploadResponse` payload across all three statuses so per-file rejection diagnostics are always rendered inline.
- **Conditional Status Polling (`features/documents/queries.ts`):** TanStack Query's `refetchInterval` inspects the current page and polls every `2.5s` only while at least one document is in `uploaded` or `processing` status. Once every document reaches a terminal status (`parsed` or `failed`), polling stops automatically to eliminate idle network and database load.
- **CSS Variable Theme Tokens (`src/index.css`):** Day 1 ships a restrained light theme using a zinc neutral base, an indigo primary accent, and semantic status variables (`--status-uploaded`, `--status-processing`, `--status-parsed`, `--status-failed`). Defining every color via CSS custom properties keeps dark mode a drop-in variable override for a future milestone without touching component classes.

