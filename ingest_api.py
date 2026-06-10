"""
ingest_api.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FastAPI backend — Vector Ingest + User Management + Admin Auth

Endpoints:
  POST   /auth/login              ← admin login → returns session token
  POST   /auth/logout             ← invalidate token

  POST   /ingest/url              ← scrape URL → embed → Pinecone
  POST   /ingest/pdf              ← upload PDF → embed → Pinecone
  GET    /jobs/{job_id}           ← poll job status

  GET    /users                   ← list all app users
  POST   /users                   ← create user
  DELETE /users/{user_id}         ← delete user

All routes except /auth/login require:
  Header:  x-api-key: <ADMIN_API_KEY>   (machine-to-machine, e.g. from dashboard)
  OR       Authorization: Bearer <session_token>  (from /auth/login)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os, re, time, uuid, json, hashlib, secrets
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
from pinecone import Pinecone
from dotenv import load_dotenv
from utils.language_detector import detect_language

load_dotenv()

app = FastAPI(title="Vector Admin API", version="1.0.0")

# ── CORS ───────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "null",   # covers opening admin.html directly as a local file
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ─────────────────────────────────────────────────────
PINECONE_API_KEY  = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX    = os.getenv("PINECONE_INDEX", "pregnancy-knowledge")
PINECONE_HOST     = os.getenv("PINECONE_HOST")
MISTRAL_API_KEY   = os.getenv("MISTRAL_API_KEY")
ADMIN_API_KEY     = os.getenv("ADMIN_API_KEY", "")
ADMIN_EMAIL       = os.getenv("ADMIN_EMAIL", "admin@gmail.com")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "admin123")
USERS_FILE        = os.getenv("USERS_FILE", "data/users.json")
NGO_FILE          = os.getenv("NGO_FILE", "data/ngos.json")
PDF_FOLDER        = "pdfs"
SESSION_TTL_HOURS = 24

os.makedirs(PDF_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(USERS_FILE) if os.path.dirname(USERS_FILE) else ".", exist_ok=True)

pc = Pinecone(api_key=PINECONE_API_KEY)

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── In-memory stores ───────────────────────────────────────────
JOBS: Dict[str, Dict] = {}
SESSIONS: Dict[str, Dict] = {}   # token → {email, expires_at}


# ══════════════════════════════════════════════════════════════
# SERVE ADMIN HTML (same-origin — no CORS needed when using this)
# ══════════════════════════════════════════════════════════════

@app.get("/admin", tags=["Admin"], include_in_schema=False)
def serve_admin():
    """Serve admin.html from the project root at http://localhost:8000/admin"""
    html_path = os.path.join(os.path.dirname(__file__), "admin.html")
    if not os.path.exists(html_path):
        raise HTTPException(404, "admin.html not found next to ingest_api.py")
    return FileResponse(html_path, media_type="text/html")


# ══════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: str
    password: str


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@app.post("/auth/login", tags=["Auth"])
def login(body: LoginRequest):
    """
    Admin login. Returns a session token valid for 24 hours.
    Credentials are set via ADMIN_EMAIL / ADMIN_PASSWORD env vars
    (defaults: admin@gmail.com / admin123).
    """
    if body.email != ADMIN_EMAIL or body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = secrets.token_hex(32)
    expires = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)
    SESSIONS[token] = {"email": body.email, "expires_at": expires.isoformat()}
    return {"token": token, "expires_at": expires.isoformat(), "email": body.email}


@app.post("/auth/logout", tags=["Auth"])
def logout(authorization: Optional[str] = Header(None)):
    token = (authorization or "").replace("Bearer ", "").strip()
    SESSIONS.pop(token, None)
    return {"status": "logged out"}


def _verify(x_api_key: Optional[str] = None, authorization: Optional[str] = None):
    """
    Accepts either:
      - x-api-key header  (ADMIN_API_KEY env var)
      - Authorization: Bearer <session_token> from /auth/login
    """
    if x_api_key and ADMIN_API_KEY and x_api_key == ADMIN_API_KEY:
        return True

    token = (authorization or "").replace("Bearer ", "").strip()
    if token and token in SESSIONS:
        sess = SESSIONS[token]
        if datetime.utcnow() < datetime.fromisoformat(sess["expires_at"]):
            return True
        SESSIONS.pop(token, None)

    raise HTTPException(status_code=401, detail="Unauthorized — provide valid x-api-key or Bearer token")


def require_auth(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    return _verify(x_api_key, authorization)


# ══════════════════════════════════════════════════════════════
# USER MANAGEMENT  (flat JSON file store)
# ══════════════════════════════════════════════════════════════

class UserCreate(BaseModel):
    name: str
    email: str
    role: Optional[str] = "user"
    phone: Optional[str] = None
    notes: Optional[str] = None


def _read_users() -> List[Dict]:
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE) as f:
        return json.load(f)


def _write_users(users: List[Dict]):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


@app.get("/users", tags=["Users"])
def list_users(_auth=Depends(require_auth)):
    """Return all users."""
    return _read_users()


@app.post("/users", status_code=201, tags=["Users"])
def create_user(body: UserCreate, _auth=Depends(require_auth)):
    """Create a new user."""
    users = _read_users()
    if any(u["email"] == body.email for u in users):
        raise HTTPException(status_code=409, detail="Email already exists")
    user = {
        "id": uuid.uuid4().hex,
        "name": body.name,
        "email": body.email,
        "role": body.role,
        "phone": body.phone,
        "notes": body.notes,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    users.append(user)
    _write_users(users)
    return user


@app.delete("/users/{user_id}", tags=["Users"])
def delete_user(user_id: str, _auth=Depends(require_auth)):
    """Delete a user by id."""
    users = _read_users()
    new_users = [u for u in users if u["id"] != user_id]
    if len(new_users) == len(users):
        raise HTTPException(status_code=404, detail="User not found")
    _write_users(new_users)
    return {"deleted": user_id}


# ════════════════════════════════════════════════════════════
# NGO MANAGEMENT  (flat JSON file store)
# ════════════════════════════════════════════════════════════

class NgoCreate(BaseModel):
    organization_name: str
    email: str
    enabled: Optional[bool] = True


def _read_ngos() -> List[Dict]:
    if not os.path.exists(NGO_FILE):
        return []
    with open(NGO_FILE) as f:
        return json.load(f)


def _write_ngos(ngos: List[Dict]):
    with open(NGO_FILE, "w") as f:
        json.dump(ngos, f, indent=2)


@app.get("/ngos", tags=["NGOs"])
def list_ngos(_auth=Depends(require_auth)):
    """Return all NGOs."""
    return _read_ngos()


@app.post("/ngos", status_code=201, tags=["NGOs"])
def create_ngo(body: NgoCreate, _auth=Depends(require_auth)):
    """Create a new NGO entry."""
    ngos = _read_ngos()
    if any(n["email"] == body.email for n in ngos):
        raise HTTPException(status_code=409, detail="Email already exists")
    ngo = {
        "id": uuid.uuid4().hex,
        "organization_name": body.organization_name,
        "email": body.email,
        "enabled": body.enabled if body.enabled is not None else True,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    ngos.append(ngo)
    _write_ngos(ngos)
    return ngo


@app.delete("/ngos/{ngo_id}", tags=["NGOs"])
def delete_ngo(ngo_id: str, _auth=Depends(require_auth)):
    """Delete an NGO by id."""
    ngos = _read_ngos()
    new_ngos = [n for n in ngos if n["id"] != ngo_id]
    if len(new_ngos) == len(ngos):
        raise HTTPException(status_code=404, detail="NGO not found")
    _write_ngos(new_ngos)
    return {"deleted": ngo_id}


@app.patch("/ngos/{ngo_id}/toggle", tags=["NGOs"])
def toggle_ngo(ngo_id: str, _auth=Depends(require_auth)):
    """Toggle an NGO's enabled/disabled status."""
    ngos = _read_ngos()
    for ngo in ngos:
        if ngo["id"] == ngo_id:
            ngo["enabled"] = not ngo.get("enabled", True)
            _write_ngos(ngos)
            return ngo
    raise HTTPException(status_code=404, detail="NGO not found")


# ══════════════════════════════════════════════════════════════
# STATS  —  Pinecone index overview
# ══════════════════════════════════════════════════════════════

@app.get("/stats", tags=["Stats"])
def get_stats(_auth=Depends(require_auth)):
    """Return Pinecone index statistics (vector counts per namespace)."""
    try:
        index = get_index()
        raw = index.describe_index_stats()
        # raw is a dict-like object; normalise into a plain dict
        ns_raw = getattr(raw, "namespaces", None) or raw.get("namespaces", {})
        namespaces = {}
        for ns_name, ns_info in ns_raw.items():
            # Pinecone SDK v3 returns objects; older versions return dicts
            if hasattr(ns_info, "vector_count"):
                count = ns_info.vector_count
            elif isinstance(ns_info, dict):
                count = ns_info.get("vector_count", ns_info.get("vectorCount", 0))
            else:
                count = 0
            namespaces[ns_name] = {"vector_count": count}

        total = getattr(raw, "total_vector_count", None)
        if total is None:
            total = raw.get("total_vector_count", raw.get("totalVectorCount", 0))

        dimension = getattr(raw, "dimension", None)
        if dimension is None:
            dimension = raw.get("dimension", 1024)

        return {
            "total_vector_count": total,
            "dimension": dimension,
            "namespaces": namespaces,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Pinecone stats: {e}")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return JSONResponse(status_code=204, content=None)


# ══════════════════════════════════════════════════════════════
# HELPERS — embedding + chunking
# ══════════════════════════════════════════════════════════════

def get_index():
    return pc.Index(name=PINECONE_INDEX, host=PINECONE_HOST)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_mostly_text(text: str) -> bool:
    if not text or len(text.strip()) < 50:
        return False
    bad = sum(1 for c in text if c in ("?", "□", "▯", "\ufffd"))
    return (bad / len(text)) < 0.3


def merge_paragraphs(lines, min_words=10, max_words=120):
    merged, buffer = [], ""
    for line in lines:
        if len(line.split()) < min_words:
            continue
        combined = (buffer + " " + line).strip() if buffer else line
        if len(combined.split()) <= max_words:
            buffer = combined
        else:
            if buffer:
                merged.append(buffer)
            buffer = line
    if buffer:
        merged.append(buffer)
    return merged


def extract_paragraphs_from_soup(elem):
    MIN_WORDS, MAX_WORDS = 15, 120
    raw = []
    for tag in elem.find_all(["p", "li", "h2", "h3"]):
        text = re.sub(r"\s+", " ", tag.get_text(separator=" ", strip=True))
        if len(text.split()) >= MIN_WORDS:
            raw.append(text)
    merged, buffer = [], ""
    for para in raw:
        combined = (buffer + " " + para).strip() if buffer else para
        if len(combined.split()) <= MAX_WORDS:
            buffer = combined
        else:
            if buffer:
                merged.append(buffer)
            buffer = para
    if buffer:
        merged.append(buffer)
    return merged


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.mistral.ai/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {MISTRAL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": "mistral-embed", "input": texts},
                timeout=60,
            )
            resp.raise_for_status()
            return [item["embedding"] for item in resp.json()["data"]]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


# ══════════════════════════════════════════════════════════════
# JOB STORE
# ══════════════════════════════════════════════════════════════

def create_job(job_type, payload, webhook_url=None):
    job_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat() + "Z"
    JOBS[job_id] = {
        "id": job_id,
        "type": job_type,
        "payload": payload,
        "status": "queued",
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
        "webhook_url": webhook_url,
    }
    return job_id


def finalize_job(job_id, result=None, error=None):
    job = JOBS.get(job_id)
    if not job:
        return
    job["status"] = "failed" if error else "done"
    job["error"] = error
    job["result"] = result
    job["finished_at"] = datetime.utcnow().isoformat() + "Z"
    if job.get("webhook_url"):
        try:
            requests.post(
                job["webhook_url"],
                json={"job_id": job_id, "status": job["status"], "result": result, "error": error},
                timeout=10,
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# INGEST — URL
# ══════════════════════════════════════════════════════════════

class URLIngest(BaseModel):
    url: str
    namespace: Optional[str] = "workspace"
    webhook_url: Optional[str] = None


def scrape_and_upsert(url: str, namespace: str = "workspace"):
    resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    elem = (
        soup.select_one("main")
        or soup.select_one("article")
        or soup.select_one("#content")
        or soup.body
    )
    title_text = soup.find("title").get_text(strip=True) if soup.find("title") else url
    paragraphs = extract_paragraphs_from_soup(elem)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", url.replace("https://", "").replace("http://", ""))

    # Detect language once per URL (same language for all chunks from this page)
    language = detect_language(url=url)

    chunks = [
        {
            "id": f"{safe_id}_p{i}"[:512],
            "text": p,
            "metadata": {
                "url": url,
                "title": title_text,
                "text": p,
                "paragraph_index": i,
                "language": language,
            },
        }
        for i, p in enumerate(paragraphs)
    ]

    all_vectors = []
    for i in range(0, len(chunks), 16):
        batch = chunks[i : i + 16]
        embeddings = embed_texts([c["text"] for c in batch])
        for c, emb in zip(batch, embeddings):
            all_vectors.append({"id": c["id"], "values": emb, "metadata": c["metadata"]})

    index = get_index()
    for i in range(0, len(all_vectors), 100):
        index.upsert(vectors=all_vectors[i : i + 100], namespace=namespace)

    return {"documents": 1, "chunks": len(chunks), "vectors": len(all_vectors)}


def run_scrape_job(job_id: str, url: str, namespace: str = "workspace"):
    job = JOBS.get(job_id)
    if not job:
        return
    job["status"] = "running"
    job["started_at"] = datetime.utcnow().isoformat() + "Z"
    try:
        finalize_job(job_id, result=scrape_and_upsert(url, namespace))
    except Exception as e:
        finalize_job(job_id, error=str(e))


@app.post("/ingest/url", status_code=202, tags=["Ingest"])
def ingest_url(payload: URLIngest, background_tasks: BackgroundTasks, _auth=Depends(require_auth)):
    """Scrape a URL, embed, and push to Pinecone (async)."""
    if not payload.url:
        raise HTTPException(400, "Missing url")
    job_id = create_job("url", {"url": payload.url, "namespace": payload.namespace}, payload.webhook_url)
    background_tasks.add_task(run_scrape_job, job_id, payload.url, payload.namespace or "workspace")
    return {"status": "accepted", "job_id": job_id}


# ══════════════════════════════════════════════════════════════
# INGEST — PDF
# ══════════════════════════════════════════════════════════════

def process_pdf_and_upsert(pdf_path: str, namespace: str = "workspace"):
    try:
        import pdfplumber
    except Exception:
        return {"error": "pdfplumber not installed — run: pip install pdfplumber"}

    all_chunks = []
    filename = os.path.basename(pdf_path)
    language = detect_language(filename=filename)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            meta = pdf.metadata or {}
            title = meta.get("Title") or meta.get("title") or filename.replace(".pdf", "")
            total_pages = len(pdf.pages)
            need_ocr = any(not is_mostly_text(p.extract_text() or "") for p in pdf.pages)

            if not need_ocr:
                for page_num, page in enumerate(pdf.pages, 1):
                    lines = [clean(l) for l in (page.extract_text() or "").split("\n")]
                    for i, para in enumerate(merge_paragraphs(lines)):
                        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
                        all_chunks.append({
                            "id": f"{safe_id}_p{page_num}_{i}"[:512],
                            "text": para,
                            "metadata": {
                                "filename": filename,
                                "title": title,
                                "text": para,
                                "page_number": page_num,
                                "total_pages": total_pages,
                                "paragraph_index": i,
                                "language": language,
                            },
                        })
            else:
                try:
                    from pdf2image import convert_from_path
                    import pytesseract
                    pytesseract.pytesseract.tesseract_cmd = os.getenv(
                        "TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                    )
                    images = convert_from_path(
                        pdf_path, dpi=300, poppler_path=os.getenv("POPPLER_PATH")
                    )
                    for page_num, image in enumerate(images, 1):
                        text = pytesseract.image_to_string(
                            image, lang=os.getenv("OCR_LANG", "ben+eng")
                        )
                        lines = [clean(l) for l in text.split("\n")]
                        for i, para in enumerate(merge_paragraphs(lines)):
                            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
                            # Re-detect per-chunk for OCR (mixed pages possible)
                            chunk_language = detect_language(filename=filename, text=para)
                            all_chunks.append({
                                "id": f"{safe_id}_ocr_p{page_num}_{i}"[:512],
                                "text": para,
                                "metadata": {
                                    "filename": filename,
                                    "title": title,
                                    "text": para,
                                    "page_number": page_num,
                                    "total_pages": len(images),
                                    "paragraph_index": i,
                                    "extraction": "ocr",
                                    "language": chunk_language,
                                },
                            })
                except Exception as e:
                    return {"error": f"OCR failed: {e}"}
    except Exception as e:
        return {"error": f"Failed to open PDF: {e}"}

    all_vectors = []
    for i in range(0, len(all_chunks), 16):
        batch = all_chunks[i : i + 16]
        embeddings = embed_texts([c["text"] for c in batch])
        for c, emb in zip(batch, embeddings):
            all_vectors.append({"id": c["id"], "values": emb, "metadata": c["metadata"]})

    index = get_index()
    for i in range(0, len(all_vectors), 100):
        index.upsert(vectors=all_vectors[i : i + 100], namespace=namespace)

    return {"documents": 1, "chunks": len(all_chunks), "vectors": len(all_vectors)}


def run_pdf_job(job_id: str, pdf_path: str, namespace: str = "workspace"):
    job = JOBS.get(job_id)
    if not job:
        return
    job["status"] = "running"
    job["started_at"] = datetime.utcnow().isoformat() + "Z"
    try:
        finalize_job(job_id, result=process_pdf_and_upsert(pdf_path, namespace))
    except Exception as e:
        finalize_job(job_id, error=str(e))


@app.post("/ingest/pdf", status_code=202, tags=["Ingest"])
def ingest_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    namespace: Optional[str] = Form("workspace"),
    webhook_url: Optional[str] = Form(None),
    _auth=Depends(require_auth),
):
    """Upload a PDF, embed, push to Pinecone (async)."""
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF uploads are supported")
    save_path = os.path.join(PDF_FOLDER, file.filename)
    with open(save_path, "wb") as f:
        f.write(file.file.read())
    job_id = create_job("pdf", {"filename": file.filename, "namespace": namespace}, webhook_url)
    background_tasks.add_task(run_pdf_job, job_id, save_path, namespace or "workspace")
    return {"status": "accepted", "job_id": job_id}


# ══════════════════════════════════════════════════════════════
# JOBS
# ══════════════════════════════════════════════════════════════

@app.get("/jobs", tags=["Jobs"])
def list_jobs(_auth=Depends(require_auth)):
    """Return all jobs (most recent first)."""
    return sorted(JOBS.values(), key=lambda j: j["created_at"], reverse=True)


@app.get("/jobs/{job_id}", tags=["Jobs"])
def get_job(job_id: str, _auth=Depends(require_auth)):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ── Run ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ingest_api:app", host="0.0.0.0", port=8000, reload=True)