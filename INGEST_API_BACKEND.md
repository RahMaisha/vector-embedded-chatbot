**Ingest API — Backend (Python) Quickstart**

Purpose
- FastAPI service that ingests a URL or PDF, creates embeddings (Mistral), and upserts vectors to Pinecone.

Key files
- `ingest_api.py` — main FastAPI service (endpoints, job tracking, OCR fallback).
- `pdf-to-pinecone.py`, `3-embedding-pinecone.py` — original CLI scripts (reference).

Environment variables (required)
- `PINECONE_API_KEY` — Pinecone API key
- `PINECONE_HOST` — Pinecone host URL
- `PINECONE_INDEX` — Pinecone index name
- `MISTRAL_API_KEY` — Mistral embeddings API key
- `ADMIN_API_KEY` or `ADMIN_API_KEYS` — comma-separated admin keys for `x-api-key`

Optional / OCR
- `TESSERACT_PATH` — path to Tesseract executable (default: `C:\Program Files\Tesseract-OCR\tesseract.exe`)
- `POPPLER_PATH` — poppler `bin` path for `pdf2image` (default: `C:\poppler\Library\bin`)
- `OCR_LANG` — tesseract languages (e.g. `ben+eng`)

Install & run
1. Create venv and install deps:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pdf2image pytesseract
```
2. Start service:
```bash
uvicorn ingest_api:app --host 0.0.0.0 --port 8000
```

API endpoints
- POST `/ingest/url`
  - Headers: `x-api-key: <ADMIN_API_KEY>`
  - Body JSON: `{ "url":"https://...", "namespace":"workspace", "webhook_url":"https://..." }`
  - Response: `202 { "status":"accepted","job_id":"..." }`

- POST `/ingest/pdf`
  - Headers: `x-api-key: <ADMIN_API_KEY>`
  - Multipart form: `file` (PDF), optional `namespace`, optional `webhook_url`
  - Response: `202 { "status":"accepted","job_id":"..." }`

- GET `/jobs/{job_id}`
  - Headers: `x-api-key: <ADMIN_API_KEY>`
  - Returns job status and result JSON

Webhook
- If `webhook_url` provided in request, backend POSTs job result `{ job_id, status, result, error }` when finished (best-effort).

OCR notes
- service tries `pdfplumber` first; if pages appear scanned/non-text it falls back to `pdf2image + pytesseract`.
- Install Tesseract + Poppler on server for OCR.

Production recommendations
- Do not expose `ADMIN_API_KEY` to browsers. Use a server-side proxy (Next.js, Supabase function, etc.).
- Replace in-memory `JOBS` with persistent store (Supabase/Redis/Postgres) to survive restarts.
- Use a task queue (Celery/RQ) for retries/long-running jobs in production.

Example curl
```bash
curl -X POST http://localhost:8000/ingest/url \
  -H "Content-Type: application/json" \
  -H "x-api-key: supersecret" \
  -d '{"url":"https://example.com/article","namespace":"workspace"}'

curl -X POST http://localhost:8000/ingest/pdf \
  -H "x-api-key: supersecret" \
  -F "file=@/path/to/file.pdf" \
  -F "namespace=workspace"
```

See also: `INGEST_API.md` for general integration notes and Next.js example in `admin-nextjs-example/`.
