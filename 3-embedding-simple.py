import requests
from bs4 import BeautifulSoup
import lancedb
from mistralai import Mistral
from dotenv import load_dotenv
import os

load_dotenv()

# Initialize Mistral client
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# Quality sources that don't block scrapers (NHS, MedlinePlus, CDC)
SOURCES = [
    {"url": "https://www.nhs.uk/pregnancy/keeping-well/have-a-healthy-diet/",           "selector": "article"},
    {"url": "https://www.nhs.uk/pregnancy/keeping-well/vitamins-supplements-and-nutrition/", "selector": "article"},
    {"url": "https://www.nhs.uk/pregnancy/keeping-well/foods-to-avoid/",                "selector": "article"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000584.htm",               "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000487.htm",               "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000622.htm",               "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000623.htm",               "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/patientinstructions/000624.htm",               "selector": "#ency-content"},
    {"url": "https://medlineplus.gov/ency/article/002398.htm",                           "selector": "#ency-content"},
    {"url": "https://www.cdc.gov/pregnancy/nutrition/index.html",                        "selector": "main"},
]

# ──────────────────────────────────────────────
# STEP 1: Extract content
# ──────────────────────────────────────────────

print("=" * 60)
print("STEP 1: Extracting content")
print("=" * 60)

chunks = []

for source in SOURCES:
    url = source["url"]
    print(f"\nFetching: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        # Try configured selector first, then fallbacks
        content_elem = soup.select_one(source["selector"])
        if not content_elem:
            for sel in ["main", "article", "#content"]:
                content_elem = soup.select_one(sel)
                if content_elem:
                    break

        if content_elem:
            text = content_elem.get_text(separator=" ", strip=True)
        else:
            text = " ".join(p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30)

        if len(text) < 200:
            print(f"  ✗ Too little content, skipping")
            continue

        print(f"  ✓ Extracted {len(text):,} characters")

        # Chunk by words (~200 words each)
        words = text.split()
        chunk_size = 200
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else url

        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunks.append({
                "text": " ".join(chunk_words),
                "metadata": {"source": url, "title": title_text, "chunk_index": i // chunk_size}
            })

        print(f"  ✓ Created {len(words) // chunk_size + 1} chunks")

    except Exception as e:
        print(f"  ✗ Failed: {e}")

if not chunks:
    print("\n⚠️  No chunks created!")
    exit(1)

print(f"\n✓ Total chunks: {len(chunks)}")

# ──────────────────────────────────────────────
# STEP 2: Embed with Mistral
# ──────────────────────────────────────────────

print("\n" + "=" * 60)
print("STEP 2: Embedding chunks with Mistral")
print("=" * 60)

BATCH_SIZE = 10  # Mistral embed supports batches

for i in range(0, len(chunks), BATCH_SIZE):
    batch = chunks[i:i + BATCH_SIZE]
    texts = [c["text"] for c in batch]
    print(f"  Embedding {i + 1}–{min(i + BATCH_SIZE, len(chunks))} / {len(chunks)}...")
    try:
        response = client.embeddings.create(model="mistral-embed", inputs=texts)
        for chunk, embedding_obj in zip(batch, response.data):
            chunk["vector"] = embedding_obj.embedding
    except Exception as e:
        print(f"  ✗ Embedding failed: {e}")
        for chunk in batch:
            chunk["vector"] = [0.0] * 1024

print("✓ All chunks embedded")

# ──────────────────────────────────────────────
# STEP 3: Store in LanceDB
# ──────────────────────────────────────────────

print("\n" + "=" * 60)
print("STEP 3: Storing in LanceDB")
print("=" * 60)

os.makedirs("data/lancedb", exist_ok=True)
db = lancedb.connect("data/lancedb")

data = [
    {
        "text": c["text"],
        "vector": c["vector"],
        "source": c["metadata"]["source"],
        "title": c["metadata"]["title"],
        "chunk_index": c["metadata"]["chunk_index"],
    }
    for c in chunks
]

table = db.create_table("pregnancy_guide", data=data, mode="overwrite")

print(f"✓ Stored {len(data)} chunks in LanceDB")
print(f"✓ Database: data/lancedb")
print("\n🎉 Done! Run: streamlit run 5-chat.py")