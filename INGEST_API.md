**Ingest API — Usage & Integration**

Overview
- Small Python FastAPI service that ingests URLs and PDFs, creates embeddings (Mistral), and upserts vectors to Pinecone.
- Endpoints return a `job_id`; jobs are processed in background and can optionally POST results to a `webhook_url`.

APIs
- **POST /ingest/url**
  - Auth: header `x-api-key`
  - Body (JSON): `{ "url": "https://...", "namespace": "workspace", "webhook_url": "https://..." }`
  - Response: 202 Accepted, `{ "status": "accepted", "job_id": "..." }`

- **POST /ingest/pdf**
  - Auth: header `x-api-key`
  - Multipart form fields: `file` (PDF), `namespace` (optional), `webhook_url` (optional)
  - Response: 202 Accepted, `{ "status": "accepted", "job_id": "..." }`

- **GET /jobs/{job_id}**
  - Auth: header `x-api-key`
  - Returns job object with keys: `id, type, status, created_at, started_at, finished_at, result, error`.

Webhooks
- Provide `webhook_url` in request body/form. When job finishes the service will POST JSON `{ job_id, status, result, error }` to that URL (best-effort; failures are ignored).

Environment variables (Python ingest service)
- `PINECONE_API_KEY` — Pinecone API key
- `PINECONE_HOST` — Pinecone host (e.g. https://xyz.pinecone.io)
- `PINECONE_INDEX` — Pinecone index name
- `MISTRAL_API_KEY` — Mistral embeddings API key
- `ADMIN_API_KEY` or `ADMIN_API_KEYS` — comma-separated admin API key(s) required by `x-api-key`
- `TESSERACT_PATH` — (optional) path to tesseract executable for OCR fallback; default: `C:\Program Files\Tesseract-OCR\tesseract.exe`
- `POPPLER_PATH` — (optional) path to poppler binaries for `pdf2image`; default: `C:\poppler\Library\bin`
- `OCR_LANG` — languages for tesseract (example: `ben+eng`)

Run locally (Python)
- Create venv and install deps (ensure tesseract + poppler installed for OCR):
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pdf2image pytesseract
```
- Set required env vars (example PowerShell):
```powershell
$env:PINECONE_API_KEY="your_key"
$env:PINECONE_HOST="https://your-index-host.pinecone.io"
$env:PINECONE_INDEX="pregnancy-knowledge"
$env:MISTRAL_API_KEY="your_mistral_key"
$env:ADMIN_API_KEY="supersecret"
# Optional OCR
$env:TESSERACT_PATH="C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:POPPLER_PATH="C:\poppler\Library\bin"
$env:OCR_LANG="ben+eng"
uvicorn ingest_api:app --host 0.0.0.0 --port 8000
```

Next.js / Frontend integration
- Two approaches:
  1) Server-proxy (recommended: keep admin key server-side): create Next.js API route that calls Python service using `INGEST_API_URL` and `INGEST_API_KEY`.
     - Env (server): `INGEST_API_URL`, `INGEST_API_KEY`.
     - Example file provided: `admin-nextjs-example/pages/api/proxy/ingest-url.js`.
  2) Direct client upload (simpler for quick setups) — client sends `x-api-key` and form data directly to Python service.
     - If using client-facing key, set `NEXT_PUBLIC_INGEST_API_KEY` and `NEXT_PUBLIC_INGEST_API_URL` (NOT recommended for production).

Example curl
- Ingest URL (server or client with valid API key):
```bash
curl -X POST http://localhost:8000/ingest/url \
  -H "Content-Type: application/json" \
  -H "x-api-key: supersecret" \
  -d '{"url":"https://example.com/article","namespace":"workspace"}'
```

- Upload PDF:
```bash
curl -X POST http://localhost:8000/ingest/pdf \
  -H "x-api-key: supersecret" \
  -F "file=@/path/to/file.pdf" \
  -F "namespace=workspace"
```

Admin UI examples in this repo
- `admin_dashboard.html` — static demo (opens in browser, uses same-origin requests to Python service).
- `admin-nextjs-example/` — Next.js example: `pages/admin.js` (client UI); `pages/api/proxy/ingest-url.js` (server proxy example); `pages/api/proxy/ingest-pdf.js` (placeholder explaining multipart server proxying).

Notes & production recommendations
- Current job store is in-memory (`JOBS`) — process restart will lose state. For production use Supabase/Redis/Postgres to persist jobs.
- For reliable background processing and retries, replace `BackgroundTasks` with a worker system (Celery, RQ, or a serverless job queue).
- Do not expose `ADMIN_API_KEY` in browser. Use a server-side proxy with authentication.

Questions or next steps
- I can implement server-side PDF proxy parsing in the Next.js example (using `formidable`) or wire Supabase auth to the admin UI. Which should I do next?
