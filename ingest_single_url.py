"""
Ingest a single URL: scrape, chunk, embed, and upsert to Pinecone.
Usage:
  python ingest_single_url.py --url "https://example.com/article"
"""
import os
import re
import time
import argparse
import requests
from bs4 import BeautifulSoup
from utils.language_detector import detect_language
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(name=os.getenv("PINECONE_INDEX", "pregnancy-knowledge"), host=os.getenv("PINECONE_HOST"))
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NAMESPACE = "workspace"

MIN_WORDS = 15
MAX_WORDS = 120

HEADERS = {"User-Agent":"Mozilla/5.0"}


def extract_paragraphs_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script','style','nav','footer','header']):
        tag.decompose()
    raw = []
    for tag in soup.find_all(['p','li','h2','h3']):
        text = re.sub(r"\s+"," ", tag.get_text(separator=' ', strip=True))
        if len(text.split()) >= MIN_WORDS:
            raw.append(text)
    # merge short paragraphs
    merged, buffer = [], ''
    for para in raw:
        combined = (buffer + ' ' + para).strip() if buffer else para
        if len(combined.split()) <= MAX_WORDS:
            buffer = combined
        else:
            if buffer:
                merged.append(buffer)
            buffer = para
    if buffer:
        merged.append(buffer)
    return merged


def embed_texts(texts):
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.mistral.ai/v1/embeddings",
                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
                json={"model":"mistral-embed","input":texts},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return [item['embedding'] for item in data['data']]
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
            else:
                raise


def upsert_vectors(vectors):
    # upsert in batches
    BATCH = 100
    for i in range(0, len(vectors), BATCH):
        batch = vectors[i:i+BATCH]
        index.upsert(vectors=batch, namespace=NAMESPACE)


def ingest_url(url, selector=None):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return {"status":"error","detail":str(e)}

    html = resp.content
    paragraphs = extract_paragraphs_from_html(html)
    # extract title
    soup = BeautifulSoup(html, 'html.parser')
    title_tag = soup.find('title')
    title_text = title_tag.get_text(strip=True) if title_tag else url
    if not paragraphs:
        return {"status":"no_paragraphs"}

    vectors = []
    safe_id = url.replace('https://','').replace('http://','').replace('/','_').replace('.','_')
    embeddings = embed_texts(paragraphs)
    for i, (para, emb) in enumerate(zip(paragraphs, embeddings)):
        vectors.append({
            'id': f"{safe_id}_p{i}"[:512],
            'values': emb,
            'metadata': {
                'url': url,
                'title': title_text,
                'text': para,
                'paragraph_index': i,
                'language': detect_language(url=url, text=para),
            }
        })

    upsert_vectors(vectors)
    return {"status":"ok","chunks":len(vectors)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    out = ingest_url(args.url)
    print(out)
