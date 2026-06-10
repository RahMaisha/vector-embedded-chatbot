"""
pdf-to-pinecone.py
━━━━━━━━━━━━━━━━━━
Supports both normal PDFs and Bangla/Bengali PDFs via OCR.
- Normal PDFs  → pdfplumber text extraction
- Bangla PDFs  → pdf2image + pytesseract OCR (ben+eng)
- Chunks paragraph by paragraph
- Embeds with Mistral API (mistral-embed, 1024-dim)
- Upserts to Pinecone under namespace: "workspace"

Requirements:
  pip install pdfplumber pdf2image pytesseract
  + Tesseract OCR installed with Bengali language pack
  Download: https://github.com/UB-Mannheim/tesseract/wiki
"""

import os
import re
import time
import glob
import requests
from pinecone import Pinecone
from dotenv import load_dotenv
from typing import List, Dict
from utils.language_detector import detect_language
import warnings
warnings.filterwarnings("ignore")  # suppress font errors

FORCE_OCR = True  # skip pdfplumber, go straight to OCR
load_dotenv()

# ── Clients ────────────────────────────────────────────────────
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(
    name=os.getenv("PINECONE_INDEX", "pregnancy-knowledge"),
    host=os.getenv("PINECONE_HOST")
)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NAMESPACE       = "workspace"
PDF_FOLDER      = "pdfs"

# ── Tesseract path (update if yours is different) ──────────────
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# OCR language: Bengali + English
# If your PDF is Bangla only, use "ben"
# If mixed Bangla+English, use "ben+eng"
OCR_LANG = "ben+eng"

MIN_WORDS = 10
MAX_WORDS = 120

# ── Check dependencies ─────────────────────────────────────────
try:
    import pdfplumber
except ImportError:
    print("❌ Run: pip install pdfplumber")
    exit(1)

try:
    from pdf2image import convert_from_path
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    OCR_AVAILABLE = os.path.exists(TESSERACT_PATH)
    if not OCR_AVAILABLE:
        print(f"⚠ Tesseract not found at: {TESSERACT_PATH}")
        print(f"  Download: https://github.com/UB-Mannheim/tesseract/wiki")
        print(f"  Then update TESSERACT_PATH in this script")
except ImportError:
    OCR_AVAILABLE = False
    print("⚠ OCR not available. Run: pip install pdf2image pytesseract")

# ── Helpers ────────────────────────────────────────────────────

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def merge_paragraphs(lines: List[str]) -> List[str]:
    """Merge short lines into paragraphs up to MAX_WORDS."""
    merged, buffer = [], ""
    for line in lines:
        if len(line.split()) < MIN_WORDS:
            continue
        combined = (buffer + " " + line).strip() if buffer else line
        if len(combined.split()) <= MAX_WORDS:
            buffer = combined
        else:
            if buffer:
                merged.append(buffer)
            buffer = line
    if buffer:
        merged.append(buffer)
    return merged

def is_mostly_text(text: str) -> bool:
    """Check if extracted text looks valid (not garbled)."""
    if not text or len(text.strip()) < 50:
        return False
    # If more than 30% chars are replacement/unknown, it's garbled
    bad = sum(1 for c in text if c in ("?", "□", "▯", "\ufffd"))
    return (bad / len(text)) < 0.3

def extract_with_pdfplumber(pdf_path: str) -> List[Dict]:
    """Extract text using pdfplumber (works for normal PDFs)."""
    chunks = []
    filename = os.path.basename(pdf_path)
    language = detect_language(filename=filename)

    with pdfplumber.open(pdf_path) as pdf:
        meta  = pdf.metadata or {}
        title = meta.get("Title") or meta.get("title") or filename.replace(".pdf", "")
        total_pages = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""

            if not is_mostly_text(text):
                return []  # Signal: fall back to OCR

            lines = [clean(l) for l in text.split("\n")]
            paragraphs = merge_paragraphs(lines)

            for i, para in enumerate(paragraphs):
                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
                language = detect_language(filename=filename, text=para)
                chunks.append({
                    "id": f"{safe_id}_p{page_num}_{i}"[:512],
                    "text": para,
                    "metadata": {
                        "filename":        filename,
                        "title":           title,
                        "text":            para,
                        "page_number":     page_num,
                        "total_pages":     total_pages,
                        "paragraph_index": i,
                        "extraction":      "pdfplumber",
                        "language":        language,
                    },
                })

    return chunks

def extract_with_ocr(pdf_path: str) -> List[Dict]:
    """Extract text using OCR — required for Bangla/scanned PDFs."""
    if not OCR_AVAILABLE:
        print(f"  ✗ OCR not available. Install Tesseract with Bengali pack.")
        return []

    chunks = []
    filename = os.path.basename(pdf_path)
    title    = filename.replace(".pdf", "")
    language = detect_language(filename=filename)

    print(f"  🔍 Running OCR ({OCR_LANG})... this may take a minute per page")

    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=r"C:\poppler\Library\bin")
        total_pages = len(images)

        for page_num, image in enumerate(images, start=1):
            print(f"     OCR page {page_num}/{total_pages}...")
            text = pytesseract.image_to_string(image, lang=OCR_LANG)

            lines = [clean(l) for l in text.split("\n")]
            paragraphs = merge_paragraphs(lines)

            for i, para in enumerate(paragraphs):
                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
                language = detect_language(filename=filename, text=para)
                chunks.append({
                    "id": f"{safe_id}_ocr_p{page_num}_{i}"[:512],
                    "text": para,
                    "metadata": {
                        "filename":        filename,
                        "title":           title,
                        "text":            para,
                        "page_number":     page_num,
                        "total_pages":     total_pages,
                        "paragraph_index": i,
                        "extraction":      "ocr",
                        "language":        language,
                    },
                })

    except Exception as e:
        print(f"  ✗ OCR failed: {e}")

    return chunks

# ── STEP 1: Find + process PDFs ────────────────────────────────

os.makedirs(PDF_FOLDER, exist_ok=True)
pdf_files = glob.glob(os.path.join(PDF_FOLDER, "*.pdf"))

if not pdf_files:
    print(f"❌ No PDFs found in '{PDF_FOLDER}/' folder.")
    print(f"   Put your PDFs in: {os.path.abspath(PDF_FOLDER)}/")
    exit(1)

print("=" * 60)
print(f"Found {len(pdf_files)} PDF(s):")
for f in pdf_files:
    print(f"  • {os.path.basename(f)}")

print("\n" + "=" * 60)
print("STEP 1: Extracting + chunking")
print("=" * 60)

all_chunks: List[Dict] = []

for pdf_path in pdf_files:
    filename = os.path.basename(pdf_path)
    print(f"\nProcessing: {filename}")
# Try normal extraction first (skip if FORCE_OCR)
    chunks = [] if FORCE_OCR else extract_with_pdfplumber(pdf_path)

    if chunks:
        print(f"  ✓ pdfplumber: {len(chunks)} chunks")
    else:
        print(f"  🔍 Using OCR mode (Bangla PDF)")
        chunks = extract_with_ocr(pdf_path)
        if chunks:
            print(f"  ✓ OCR: {len(chunks)} chunks")
        else:
            print(f"  ✗ Skipping {filename}")
            continue

    all_chunks.extend(chunks)

print(f"\n✓ {len(all_chunks)} total chunks")

if not all_chunks:
    print("❌ No chunks extracted.")
    exit(1)

# ── STEP 2: Embed with Mistral ─────────────────────────────────

print("\n" + "=" * 60)
print("STEP 2: Embedding with Mistral API")
print("=" * 60)

MISTRAL_BATCH = 16

def embed_texts(texts: List[str]) -> List[List[float]]:
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
                print(f"  ⏳ Retrying: {e}")
                time.sleep(5)
            else:
                raise

all_vectors = []
for i in range(0, len(all_chunks), MISTRAL_BATCH):
    batch = all_chunks[i : i + MISTRAL_BATCH]
    embeddings = embed_texts([c["text"] for c in batch])
    for chunk, emb in zip(batch, embeddings):
        all_vectors.append({
            "id":       chunk["id"],
            "values":   emb,
            "metadata": chunk["metadata"],
        })
    print(f"  Embedded {min(i + MISTRAL_BATCH, len(all_chunks)):>4}/{len(all_chunks)}")

# ── STEP 3: Upsert to Pinecone ─────────────────────────────────

print("\n" + "=" * 60)
print(f'STEP 3: Upserting to Pinecone — namespace="{NAMESPACE}"')
print("=" * 60)

UPSERT_BATCH = 100
for i in range(0, len(all_vectors), UPSERT_BATCH):
    batch = all_vectors[i : i + UPSERT_BATCH]
    index.upsert(vectors=batch, namespace=NAMESPACE)
    print(f"  Upserted {min(i + UPSERT_BATCH, len(all_vectors)):>4}/{len(all_vectors)}")

print(f"\n🎉 Done!")
print(f"   PDFs      : {len(pdf_files)}")
print(f"   Chunks    : {len(all_chunks)}")
print(f"   Vectors   : {len(all_vectors)}")
print(f"   Namespace : {NAMESPACE}")