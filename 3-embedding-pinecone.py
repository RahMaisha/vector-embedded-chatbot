"""
3-embedding-pinecone.py
━━━━━━━━━━━━━━━━━━━━━━━
- Scrapes NHS + MedlinePlus pregnancy pages
- Chunks paragraph-by-paragraph
- Embeds with Mistral API via raw HTTP (no mistralai package needed)
- Stores in Pinecone under namespace: "workspace"
- Metadata: url, title, text, paragraph_index
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from pinecone import Pinecone
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

# ── Clients ────────────────────────────────────────────────────
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(
    name=os.getenv("PINECONE_INDEX", "pregnancy-knowledge"),
    host=os.getenv("PINECONE_HOST")
)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NAMESPACE = "workspace"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

SOURCES = [
    # NHS
    {"url": "https://www.nhs.uk/pregnancy/keeping-well/have-a-healthy-diet/",                "selector": "article"},
    {"url": "https://www.nhs.uk/pregnancy/keeping-well/vitamins-supplements-and-nutrition/",  "selector": "article"},
    {"url": "https://www.nhs.uk/pregnancy/keeping-well/foods-to-avoid/",                      "selector": "article"},
    # MedlinePlus
    {"url": "https://medlineplus.gov/ency/patientinstructions/000584.htm", "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000603.htm", "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000617.htm", "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000544.htm", "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000950.htm", "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/pregnancyandnutrition.html",          "selector": "#topic-summary"},
    {"url": "https://medlineplus.gov/ency/article/007214.htm",             "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/pregnancy.html",                      "selector": "#topic-summary"},
]

# ── STEP 1: Scrape ─────────────────────────────────────────────

print("=" * 60)
print("STEP 1: Extracting content")
print("=" * 60)

def scrape(source: dict) -> dict | None:
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        elem = soup.select_one(source["selector"])
        if not elem:
            for sel in ["main", "article", "#content"]:
                elem = soup.select_one(sel)
                if elem:
                    break

        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else source["url"]

        return {"url": source["url"], "title": title_text, "soup_elem": elem} if elem else None

    except Exception as e:
        print(f"  ✗ {source['url']}: {e}")
        return None

documents = []
for source in SOURCES:
    print(f"\nFetching: {source['url']}")
    doc = scrape(source)
    if doc:
        documents.append(doc)
        print(f"  ✓ {doc['title']}")
    else:
        print(f"  ✗ Failed or empty")

print(f"\n✓ {len(documents)} documents fetched")

# ── STEP 2: Paragraph chunking ─────────────────────────────────

print("\n" + "=" * 60)
print("STEP 2: Paragraph chunking")
print("=" * 60)

MIN_WORDS = 15
MAX_WORDS = 120

def extract_paragraphs(elem) -> List[str]:
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

all_chunks: List[Dict] = []
for doc in documents:
    paragraphs = extract_paragraphs(doc["soup_elem"])
    for i, para in enumerate(paragraphs):
        safe_id = (
            doc["url"]
            .replace("https://", "")
            .replace("/", "_")
            .replace(".", "_")
        )
        all_chunks.append({
            "id": f"{safe_id}_p{i}"[:512],
            "text": para,
            "metadata": {
                "url": doc["url"],
                "title": doc["title"],
                "text": para,
                "paragraph_index": i,
                "total_paragraphs": len(paragraphs),
            },
        })
    print(f"  {len(paragraphs):>3} paragraphs — {doc['title'][:60]}")

print(f"\n✓ {len(all_chunks)} total chunks")

# ── STEP 3: Embed via Mistral HTTP API ─────────────────────────

print("\n" + "=" * 60)
print("STEP 3: Embedding with Mistral API (direct HTTP)")
print("=" * 60)

MISTRAL_BATCH = 16
RETRY_DELAY   = 5

def embed_texts(texts: List[str]) -> List[List[float]]:
    """Call Mistral embeddings via raw HTTP — no SDK needed."""
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
            data = resp.json()
            return [item["embedding"] for item in data["data"]]
        except Exception as e:
            if attempt < 2:
                print(f"  ⏳ Retrying ({attempt+1}/3): {e}")
                time.sleep(RETRY_DELAY)
            else:
                raise

all_vectors = []
for i in range(0, len(all_chunks), MISTRAL_BATCH):
    batch = all_chunks[i : i + MISTRAL_BATCH]
    embeddings = embed_texts([c["text"] for c in batch])
    for chunk, emb in zip(batch, embeddings):
        all_vectors.append({
            "id": chunk["id"],
            "values": emb,
            "metadata": chunk["metadata"],
        })
    print(f"  Embedded {min(i + MISTRAL_BATCH, len(all_chunks)):>3}/{len(all_chunks)}")

print(f"✓ {len(all_vectors)} vectors ready")

# ── STEP 4: Upsert to Pinecone ─────────────────────────────────

print("\n" + "=" * 60)
print(f'STEP 4: Upserting to Pinecone — namespace="{NAMESPACE}"')
print("=" * 60)

UPSERT_BATCH = 100
for i in range(0, len(all_vectors), UPSERT_BATCH):
    batch = all_vectors[i : i + UPSERT_BATCH]
    index.upsert(vectors=batch, namespace=NAMESPACE)
    print(f"  Upserted {min(i + UPSERT_BATCH, len(all_vectors)):>3}/{len(all_vectors)}")

print(f"\n🎉 Done!")
print(f"   Documents  : {len(documents)}")
print(f"   Chunks     : {len(all_chunks)}")
print(f"   Vectors    : {len(all_vectors)}")
print(f"   Namespace  : {NAMESPACE}")
print(f"   Embedding  : mistral-embed (1024-dim)")
print(f"   Metadata   : url, title, text, paragraph_index ✓")