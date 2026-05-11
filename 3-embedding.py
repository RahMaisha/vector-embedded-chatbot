from typing import List

import lancedb
from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from dotenv import load_dotenv
from lancedb.embeddings import get_registry
from lancedb.pydantic import LanceModel, Vector
from mistralai.client import Mistral
from utils.tokenizer import OpenAITokenizerWrapper
import os

load_dotenv()

# Initialize Mistral client (make sure you have MISTRAL_API_KEY in your environment variables)
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))


tokenizer = OpenAITokenizerWrapper()  # Load our custom tokenizer for OpenAI
MAX_TOKENS = 8191  # text-embedding-3-large's maximum context length


# --------------------------------------------------------------
# Extract the data from multiple URLs
# --------------------------------------------------------------

import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

urls = [
    "https://www.nhs.uk/pregnancy/keeping-well/have-a-healthy-diet/",
    "https://www.unicef.org/parenting/child-development/what-to-eat-when-pregnant",
    "https://www.unicef.org/parenting/pregnancy-milestones/first-trimester#baby-growth",
    "https://www.unicef.org/parenting/pregnancy-milestones/second-trimester",
    "https://www.unicef.org/parenting/pregnancy-milestones/third-trimester",
    "https://www.unicef.org/bangladesh/parenting-bd/your-first-trimester-guide",
    "https://www.unicef.org/bangladesh/parenting-bd/your-second-trimester-guide",
    "https://www.unicef.org/bangladesh/parenting-bd/your-third-trimester-guide"
]

docs = []
texts = []
for url in urls:
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        # Extract text from paragraphs
        text = ' '.join([p.get_text() for p in soup.find_all('p')])
        if text:
            texts.append(text)
            print(f"Extracted text from {url}: {len(text)} chars")
        else:
            print(f"No text found in {url}")
            texts.append("")
    except requests.RequestException as e:
        print(f"Failed to fetch {url}: {e}")
        texts.append("")
        continue

docs = []
for result in conv_results_iter:
    if result.document:
        docs.append(result.document)


# --------------------------------------------------------------
# Apply hybrid chunking to all documents
# --------------------------------------------------------------

# Simple chunking for text
MAX_TOKENS = 8191

chunks = []
for url, text in zip(urls, texts):
    # Simple chunking by sentences or fixed length
    sentences = text.split('. ')
    current_chunk = ""
    for sentence in sentences:
        if len((current_chunk + sentence).split()) < MAX_TOKENS // 4:  # rough estimate
            current_chunk += sentence + '. '
        else:
            if current_chunk:
                chunks.append({
                    'text': current_chunk.strip(),
                    'metadata': {
                        'filename': url,
                        'page_numbers': None,
                        'title': None
                    }
                })
            current_chunk = sentence + '. '
    if current_chunk:
        chunks.append({
            'text': current_chunk.strip(),
            'metadata': {
                'filename': url,
                'page_numbers': None,
                'title': None
            }
        })

# --------------------------------------------------------------
# Create a LanceDB database and table
# --------------------------------------------------------------

# Create a LanceDB database
db = lancedb.connect("data/lancedb")


# Custom Mistral embedding function
class MistralEmbeddingFunction:
    def __init__(self, client):
        self.client = client
        self.ndims = 1024  # Mistral embeddings dimension

    def compute_source_embeddings(self, texts):
        embeddings = []
        for text in texts:
            response = self.client.embeddings.create(
                model="mistral-embed",
                inputs=[text]
            )
            embeddings.append(response.data[0].embedding)
        return embeddings

    def SourceField(self):
        return "text"

    def VectorField(self):
        return Vector(self.ndims)

func = MistralEmbeddingFunction(client)


# Define a simplified metadata schema
class ChunkMetadata(LanceModel):
    """
    You must order the fields in alphabetical order.
    This is a requirement of the Pydantic implementation.
    """

    filename: str | None
    page_numbers: List[int] | None
    title: str | None


# Define the main Schema
class Chunks(LanceModel):
    text: str = func.SourceField()
    vector: Vector(func.ndims()) = func.VectorField()  # type: ignore
    metadata: ChunkMetadata


table = db.create_table("docling", schema=Chunks, mode="overwrite")

# --------------------------------------------------------------
# Prepare the chunks for the table
# --------------------------------------------------------------

# Create table with processed chunks
processed_chunks = [
    {
        "text": chunk.text,
        "metadata": {
            "filename": chunk.meta.origin.filename,
            "page_numbers": [
                page_no
                for page_no in sorted(
                    set(
                        prov.page_no
                        for item in chunk.meta.doc_items
                        for prov in item.prov
                    )
                )
            ]
            or None,
            "title": chunk.meta.headings[0] if chunk.meta.headings else None,
        },
    }
    for chunk in chunks
]

# --------------------------------------------------------------
# Add the chunks to the table (automatically embeds the text)
# --------------------------------------------------------------

table.add(processed_chunks)

# --------------------------------------------------------------
# Load the table
# --------------------------------------------------------------

table.to_pandas()
table.count_rows()
