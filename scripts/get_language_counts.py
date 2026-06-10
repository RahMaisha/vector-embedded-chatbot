"""
Quick verification script: print language counts and sample IDs.
Run:
    python scripts/get_language_counts.py
"""
import os
import json
from collections import Counter
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(name=os.getenv("PINECONE_INDEX"), host=os.getenv("PINECONE_HOST"))

NAMESPACE = "workspace"


def fetch_all_ids(namespace=NAMESPACE):
    ids = []
    # index.list may return a dict (single page) or a generator (paged)
    resp = index.list(namespace=namespace)
    if hasattr(resp, "get"):
        # single page dict
        batch = resp.get("vectors", [])
        ids.extend(batch)
    else:
        # generator of pages
        for page in resp:
            batch = page.get("vectors", [])
            if not batch:
                continue
            ids.extend(batch)
    return ids


def main():
    ids = fetch_all_ids()
    print(f"Found {len(ids)} vector ids")
    counts = Counter()
    sample = {}
    for i in range(0, len(ids), 100):
        batch = ids[i:i+100]
        fetched = index.fetch(ids=batch, namespace=NAMESPACE)
        for vid, data in fetched.get("vectors", {}).items():
            meta = data.get("metadata", {})
            lang = meta.get("language", "unknown")
            counts[lang] += 1
            if lang not in sample and len(sample) < 20:
                sample[lang] = vid
    print("\nLanguage counts:")
    for lang, c in counts.most_common():
        print(f"  {lang}: {c}")
    print("\nSample IDs:")
    for lang, vid in sample.items():
        print(f"  {lang}: {vid}")

if __name__ == '__main__':
    main()
