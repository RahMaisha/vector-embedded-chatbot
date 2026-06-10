# Multilingual RAG Pipeline

A production-ready Retrieval-Augmented Generation (RAG) pipeline that supports **web scraping**, **PDF extraction**, **Bangla and English documents**, and **semantic search** via vector embeddings. Drop in any URLs or PDFs, embed them, store in Pinecone, and chat with your knowledge base.

---

## What It Does

- Scrapes any website for content via configurable URLs
- Extracts text from **any PDF** — English or Bangla
- Uses **OCR** (Tesseract) automatically for Bangla PDFs or scanned documents
- Chunks content **paragraph by paragraph** for high-quality retrieval
- Embeds using **Mistral `mistral-embed`** (1024-dim vectors)
- Stores in **Pinecone** under a configurable namespace
- Export/import vectors as JSON to share knowledge bases with others
- Includes a **Streamlit chat UI** for querying the knowledge base in natural language

---

## Project Structure

```
├── pdfs/                        # Drop your PDF files here
├── utils/
│   ├── __init__.py
│   ├── sitemap.py               # Sitemap URL extractor
│   └── tokenizer.py             # OpenAI tokenizer wrapper
├── 1-extraction.py              # Web scraping with Docling
├── 2-chunking.py                # Hybrid chunking demo
├── 3-embedding.py               # LanceDB + Mistral embeddings
├── 3-embedding-pinecone.py      # Web scraping → Pinecone
├── 3-embedding-simple.py        # Web scraping → LanceDB (simple)
├── 4-search.py                  # Vector search test
├── 5-chat.py                    # Streamlit chat UI (LanceDB)
├── 5-chat-pinecone.py           # Streamlit chat UI (Pinecone) ← main app
├── pdf-to-pinecone.py           # PDF → OCR → embed → Pinecone
├── export-vectors.py            # Export Pinecone vectors to JSON
├── import-vectors.py            # Import vectors from JSON into Pinecone
├── create-index.py              # Create Pinecone index
├── requirements.txt
└── .env                         # API keys (never commit this)
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/your-repo-name.git
cd your-repo-name
```

### 2. Create and activate virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# Mac/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
pip install pdfplumber pdf2image pytesseract
```

### 4. Install Tesseract OCR (for Bangla or scanned PDFs)

Download from: https://github.com/UB-Mannheim/tesseract/wiki

During installation check **Additional language data → Bengali** (or any other language you need)

Default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`

### 5. Install Poppler (required by pdf2image)

Download from: https://github.com/oschwartz10612/poppler-windows/releases

Extract to `C:\poppler\` then either:
- Add `C:\poppler\Library\bin` to your system PATH, or
- Set `poppler_path=r"C:\poppler\Library\bin"` in `pdf-to-pinecone.py`

### 6. Configure environment variables

Create a `.env` file in the project root:

```env
MISTRAL_API_KEY=your_mistral_api_key
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_HOST=https://your-index-host.pinecone.io
PINECONE_INDEX=your-index-name
```

Get your keys from:
- Mistral: https://console.mistral.ai
- Pinecone: https://app.pinecone.io

---

## Usage

### Step 1 — Create Pinecone index (first time only)

```bash
python create-index.py
```

### Step 2 — Scrape websites and push to Pinecone

Edit the `SOURCES` list in `3-embedding-pinecone.py` to add your own URLs:

```python
SOURCES = [
    {"url": "https://yourwebsite.com/page1", "selector": "article"},
    {"url": "https://yourwebsite.com/page2", "selector": "main"},
]
```

Then run:

```bash
python 3-embedding-pinecone.py
```

### Step 3 — Process PDFs and push to Pinecone

Drop any PDF files (English, Bangla, or other languages) into the `pdfs/` folder:

```bash
python pdf-to-pinecone.py
```

The script auto-detects:
- **Normal PDFs** → fast direct text extraction
- **Bangla / scanned PDFs** → automatic OCR fallback

### Step 4 — Launch chat UI

```bash
python -m streamlit run 5-chat-pinecone.py
```

Open http://localhost:8501 in your browser and start querying your knowledge base.

---

## Sharing Your Knowledge Base

Export vectors to a JSON file and share with anyone:

```bash
python export-vectors.py
# → creates vectors-export.json
```

The recipient runs:

```bash
python import-vectors.py
# → imports into their own Pinecone index
```

No re-scraping or re-embedding needed — the full vector knowledge base transfers instantly.

---

## Customisation

| What to change | Where |
|---|---|
| URLs to scrape | `SOURCES` list in `3-embedding-pinecone.py` |
| PDF folder path | `PDF_FOLDER` in `pdf-to-pinecone.py` |
| OCR language | `OCR_LANG` in `pdf-to-pinecone.py` (e.g. `"ben+eng"`, `"ara"`, `"hin"`) |
| Pinecone namespace | `NAMESPACE` in any script |
| Chunk size | `MIN_WORDS` / `MAX_WORDS` in embedding scripts |
| Embedding model | `model` field in `embed_texts()` function |
| Chat LLM | `model` field in `chat()` in `5-chat-pinecone.py` |

---

## Tech Stack

| Component | Technology |
|---|---|
| Web scraping | `requests` + `BeautifulSoup` |
| PDF extraction | `pdfplumber` |
| OCR | `Tesseract` + `pytesseract` + `pdf2image` |
| Embeddings | Mistral `mistral-embed` (1024-dim) |
| Vector database | Pinecone (serverless) |
| Chat UI | Streamlit |
| LLM | Mistral `mistral-large-latest` |

---

## Notes

- `.env`, `pdfs/`, and `data/` are gitignored — never commit API keys or raw documents
- All vectors land in Pinecone namespace `workspace` by default — change `NAMESPACE` to segment different topics
- Bangla OCR quality depends on scan resolution — 300 DPI gives the best results
- Mistral rate limits are handled automatically with retry logic
- To use a different embedding model, update both the embedding script and `create-index.py` (dimensions must match)