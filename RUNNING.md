# How to Run the Multilingual RAG Pipeline

This document explains how to set up, run, and interact with the various components of the **Vector Embedded Chatbot** project.

---

## 1. Setup & Environment Activation

Before running any script or server, ensure you activate the virtual environment and install the required Python packages.

### Activate Virtual Environment (Windows)

*   **PowerShell:**
    ```powershell
    .venv\Scripts\Activate.ps1
    ```
*   **Command Prompt (CMD):**
    ```cmd
    .venv\Scripts\activate.bat
    ```

### Install Dependencies
```bash
pip install -r requirements.txt
pip install pdfplumber pdf2image pytesseract
```

> [!NOTE]
> Make sure your `.env` file is present in the root directory and configured with valid keys (`MISTRAL_API_KEY`, `PINECONE_API_KEY`, `PINECONE_HOST`, `PINECONE_INDEX`, and `ADMIN_API_KEY`).

---

## 2. Ingest API Backend & Admin Panel (FastAPI)

The FastAPI server handles automated ingestion requests (URL scraping, PDF uploads with optional OCR parsing) and user management.

*   **Start the service:**
    ```bash
    uvicorn ingest_api:app --host 0.0.0.0 --port 8000
    ```
*   **API Interactive Documentation:** Open `http://localhost:8000/docs` in your browser.
*   **Web Admin Console UI:** Open `http://localhost:8000/admin` in your browser to access the graphical control board.

---

## 3. Frontend Chat Client & Analytics (Streamlit)

Launch the user-facing chat interfaces or analytics dashboards using Streamlit:

*   **Streamlit Chat Interface (Pinecone index):**
    ```bash
    streamlit run 5-chat-pinecone.py
    ```
*   **Streamlit Chat Interface (LanceDB local store):**
    ```bash
    streamlit run 5-chat.py
    ```
*   **Vector Language Analytics Dashboard:**
    ```bash
    streamlit run language_dashboard.py
    ```

---

## 4. CLI Data & Ingestion Utilities (One-off Scripts)

To execute pipeline operations directly from the command line:

*   **Create Pinecone Index:**
    ```bash
    python create-index.py
    ```
*   **Web Page Scraper & Pinecone Ingest:**
    ```bash
    python 3-embedding-pinecone.py
    ```
*   **PDF Parsing, OCR & Pinecone Ingest:**
    ```bash
    python pdf-to-pinecone.py
    ```
*   **Export Vector Index to JSON:**
    ```bash
    python export-vectors.py
    ```
*   **Import Vector Index from JSON:**
    ```bash
    python import-vectors.py
    ```
