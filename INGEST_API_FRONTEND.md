**Ingest Admin — Frontend (Next.js) Quickstart**

Purpose
- Example Next.js admin panel with Supabase auth and server-side proxy routes that forward admin actions to the Python ingest API.

Key files (in this repo)
- `admin-nextjs-example/pages/admin.js` — Admin UI (magic-link sign-in via Supabase, triggers ingest actions).
- `admin-nextjs-example/pages/api/proxy/ingest-url.js` — Server proxy for URL ingest (verifies Supabase token, forwards to Python API with server-side key).
- `admin-nextjs-example/pages/api/proxy/ingest-pdf.js` — Server proxy for PDF uploads (parses multipart with `formidable`, forwards to Python API with server-side key).

Environment variables (Next.js server)
- `NEXT_PUBLIC_SUPABASE_URL` — Supabase project URL (client)
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — Supabase anon key (client)
- `SUPABASE_SERVICE_ROLE_KEY` — Supabase service role key (server-only; used to verify tokens)
- `INGEST_API_URL` — URL of Python ingest service (server-only)
- `INGEST_API_KEY` — Admin API key for Python ingest service (server-only)

Optional (client direct upload)
- `NEXT_PUBLIC_INGEST_API_URL` and `NEXT_PUBLIC_INGEST_API_KEY` (only for testing; DO NOT expose in production)

Install
```bash
# in your Next.js project
npm install @supabase/supabase-js formidable form-data
```

Run
```bash
# set env vars in .env.local or host environment
npm run dev
```

How it works
- Admin UI uses Supabase magic-link auth. After sign-in the client receives an access token.
- Client calls server proxy endpoints with `Authorization: Bearer <access_token>`.
- Server proxy verifies token using `SUPABASE_SERVICE_ROLE_KEY` and then forwards request to Python ingest API using `INGEST_API_KEY` kept server-side.

Security notes
- Never expose `SUPABASE_SERVICE_ROLE_KEY` or `INGEST_API_KEY` to the browser.
- Only allow trusted admin users in Supabase (use roles or check email against allowlist in proxy route).

Next steps / customization
- Add an allowlist in `ingest-url.js` and `ingest-pdf.js` to restrict which Supabase users can trigger ingests.
- Add a jobs dashboard that polls `GET /jobs/{job_id}` and displays status/history.
- Integrate Supabase Row Level Security (RLS) if storing job records in Supabase DB.

Notes
- The example `ingest-pdf` proxy uses `formidable` to parse uploads and `form-data` to forward files; ensure Node environment has permissions to write temp files.
- For serverless deployments, adjust temp file handling per platform.
