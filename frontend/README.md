# Research & Visual Blog Studio — Next.js 16 Frontend

Next.js 16 (App Router, React 19) UI for the FastAPI research backend. It is built as a
**static export** (`output: "export"` in `next.config.ts`) and served by FastAPI from
`frontend/out` in production, so all API calls are same-origin relative paths there.

> This is not the Next.js from older docs/training data. Read the bundled guides in
> `node_modules/next/dist/docs/` before changing routing, config, or special files.

## Local development

Two processes: FastAPI on `:8000` (from the repo root) and this UI on `:3000`.

```bash
# Terminal 1 — repo root
uv run uvicorn backend.main:app --reload --port 8000

# Terminal 2 — this directory
npm ci
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

`NEXT_PUBLIC_API_BASE` is required in development: the static export has no server-side
proxy, and Next.js **rewrites are not supported with `output: "export"`**. The value is
inlined at build time — leave it unset for production builds so the app uses relative
`/api/v1/...` URLs against the same origin. Cookies are sent with `credentials: "include"`;
the backend CORS allow-list already permits `http://localhost:3000`.

On PowerShell:

```powershell
$env:NEXT_PUBLIC_API_BASE = "http://localhost:8000"; npm run dev
```

## Scripts

| Script | Purpose |
| --- | --- |
| `npm run dev` | Next dev server |
| `npm run build` | Optimized static export into `out/` |
| `npm run typecheck` | `next typegen` + `tsc --noEmit --incremental false` |
| `npm run lint` | ESLint (fails on `any` / unused vars) |
| `npm run serve` | Serve the built `out/` locally (not needed in production; FastAPI serves it) |

## Architecture notes

- `lib/api.ts` — typed API client, configurable base URL, 30s abort/timeout (120s for
  copilot edits), typed error extraction.
- `lib/sse.ts` — resumable SSE client (`Last-Event-ID` / `after_seq`) with exponential
  backoff; after 5 failed reconnects the caller reconciles via `GET /api/v1/runs/{id}`.
- `app/page.tsx` — persists the active run id in `localStorage` and reattaches after a
  refresh (the backend allows one active run per user, so dead-ending produces a 409).
- `components/copilot-drawer.tsx` — calls `POST /api/v1/articles/{id}/edit`
  (`{"instruction": str}` → `{"success", "new_revision_num", "content"}`) and shows the
  real revision preview; no simulated typing.
- `components/diff-viewer.tsx` — parses the backend's `diff_html` into a fixed allowlist
  of row kinds and renders it as React text. It never uses `dangerouslySetInnerHTML`.
- `components/mermaid-canvas.tsx` — initializes Mermaid once with `securityLevel: "strict"`
  and keeps only the latest render (stale async renders are discarded).

## Environment variables

| Variable | Where | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE` | build/dev | Backend origin for split dev (e.g. `http://localhost:8000`). Unset in production. |

## Production build

FastAPI mounts `frontend/out` automatically when it exists. Build once with:

```bash
npm ci && npm run build
```

Then start the backend from the repo root; `/` serves the exported UI and `/api/v1/*` the API.
