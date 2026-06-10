# Language Tag Implementation Guide

## Overview

Your vector database now supports **language-aware search**. Each vector has a `language` field that enables:

✅ Automatic language detection from user queries  
✅ Filtering results by user's language  
✅ Fallback to all vectors if no matches found  
✅ Multi-language analytics  

---

## What Changed

### 1. **New Utility: Language Detector** (`utils/language_detector.py`)
Detects language from:
- File names: `pregnancy_guide_en.pdf` → `"en"`
- File names: `health_ben.pdf` → `"ben"`
- URLs: `.com/en/page` → `"en"`
- URLs: `.com/bn/page` → `"ben"`

```python
from utils.language_detector import detect_language

# From filename
lang = detect_language(filename="document_en.pdf")  # → "en"

# From URL
lang = detect_language(url="https://site.com/bn/article")  # → "ben"

# Explicit
lang = detect_language(explicit_lang="bengali")  # → "ben"
```

**Supported languages:**
- `"en"` — English
- `"ben"` — Bengali
- `"es"` — Spanish
- `"fr"` — French
- ... (easily extendable)

---

### 2. **Updated Ingestion Scripts**

#### `pdf-to-pinecone.py`
Now detects language from PDF filenames and adds it to metadata:

```python
# Example: Process both English and Bengali PDFs
# pregnancy_en.pdf     → language: "en"
# health_guide_ben.pdf → language: "ben"
# random.pdf           → language: "en" (default)
```

#### `3-embedding-pinecone.py`
Detects language from scraped URLs and adds to metadata:

```python
# NHS URL (.com/en/) → language: "en"
# Bengali URL (.com/bn/) → language: "ben"
```

---

### 3. **Migration Script** (`migrate-add-language-tag.py`)

**Safely updates ALL existing vectors** with language tags:

```bash
# Preview changes (dry run)
python migrate-add-language-tag.py --dry-run

# Apply migration
python migrate-add-language-tag.py

# Migrate specific namespace
python migrate-add-language-tag.py --namespace workspace
```

**Features:**
- ✅ Non-breaking (adds field, doesn't modify existing vectors)
- ✅ Resumable (checkpoint system for interrupted runs)
- ✅ Safe (analyzes filename/URL from existing metadata)

---

### 4. **Agent Search Utility** (`agent_search.py`)

**Primary tool for agent integration.** Detects user language and filters vectors automatically:

```python
from agent_search import search_with_language_filter, detect_query_language

# Automatic detection (recommended)
results = search_with_language_filter(
    query="What should I eat during pregnancy?",
    top_k=5,
    detect_user_language=True  # Auto-detects: "en"
)

# Force language
results = search_with_language_filter(
    query="গর্ভকালীন পুষ্টি",
    top_k=5,
    explicit_language="ben"  # Force Bengali
)

# Each result includes:
# {
#     "text": "...",
#     "title": "...",
#     "url": "...",
#     "language": "en",  # ← Language tag
#     "score": 0.85,
#     "metadata": {...}
# }
```

**Language detection:**
```python
lang = detect_query_language("গর্ভকালীন পুষ্টি")  # → "ben"
lang = detect_query_language("pregnancy")       # → "en"
```

---

## How to Use with Your Agent

### Step 1: Import the search utility

```python
from agent_search import search_with_language_filter, detect_query_language
```

### Step 2: User sends query in their language

```
User (English): "What vitamins should I take?"
User (Bengali): "আমার কী ভিটামিন নেওয়া উচিত?"
```

### Step 3: Agent searches with auto-detection

```python
user_query = "আমার কী ভিটামিন নেওয়া উচিত?"

results = search_with_language_filter(
    query=user_query,
    top_k=5,
    detect_user_language=True  # Automatically detects "ben"
)

# Returns only Bengali results (or falls back to all if none found)
```

### Step 4: Pass to LLM with context

```python
context = "\n---\n".join([
    f"[{r['title']}]\n{r['text']}\nSource: {r['url']}"
    for r in results
])

# Pass context to Mistral/OpenAI/etc
```

---

## Example: Multi-language Scenario

```python
# User asks in Bengali
query = "গর্ভাবস্থায় খাবার কী খাওয়া উচিত?"

# 1. Detect language
detected_lang = detect_query_language(query)  # → "ben"

# 2. Search with language filter
results = search_with_language_filter(
    query=query,
    top_k=5,
    detect_user_language=True
)

# 3. Results are prioritized by language
# - First 5 results from Bengali docs
# - If < 5 found, includes English docs

# 4. Pass to LLM
response = llm.generate(
    system="You are a pregnancy health assistant",
    context="\n---\n".join([r['text'] for r in results]),
    user_query=query
)
```

---

## Advanced Features

### Multi-language Search
Get results grouped by language:

```python
from agent_search import search_all_languages

grouped = search_all_languages("nutrition", top_k=3)
# {
#     "en": [...3 English results...],
#     "ben": [...3 Bengali results...],
#     "es": [...3 Spanish results...]
# }
```

### No Fallback
Strictly search in one language:

```python
results = search_with_language_filter(
    query="question",
    explicit_language="ben",
    fallback_to_all=False  # No fallback
)
```

---

## Migration Workflow

### For Existing Vectors

```bash
# 1. Backup (optional)
# Save current state or create a snapshot

# 2. Preview changes
python migrate-add-language-tag.py --dry-run

# 3. Run migration
python migrate-add-language-tag.py

# 4. Verify
# Check Pinecone console or query with language filter
```

### For New Vectors

Just run your ingestion scripts as normal:

```bash
# New PDFs automatically get language tags
python pdf-to-pinecone.py

# New URLs automatically get language tags
python 3-embedding-pinecone.py
```

---

## Metadata Structure

Each vector now has:

```python
{
    "id": "doc_p0",
    "values": [0.1, 0.2, ...],  # Vector embeddings
    "metadata": {
        "text": "...",
        "title": "...",
        "url": "https://...",
        "filename": "pregnancy_en.pdf",
        "language": "en",  # ← NEW FIELD
        "extraction": "pdfplumber",
        "page_number": 1,
        ...
    }
}
```

---

## Safety Notes

✅ **Non-breaking**: Field is optional, doesn't affect existing queries  
✅ **Reversible**: Can be removed or updated without re-embedding  
✅ **Indexed**: Language field is filterable in Pinecone  
✅ **Incremental**: Migration can resume from interruptions  
✅ **Backward compatible**: Works with vectors that have/don't have language tag  

---

## Testing

Test the language detection:

```bash
python utils/language_detector.py
```

Test the agent search:

```bash
python agent_search.py
```

---

## FAQ

**Q: What if a document has mixed languages?**  
A: Extract language from filename/URL. For mixed content, consider splitting or marking as "bilingual" (can extend language detector).

**Q: Will this re-embed vectors?**  
A: No. Language is metadata only. Embeddings stay the same.

**Q: Can I change language tags later?**  
A: Yes. Just upsert with updated metadata.

**Q: What if language detection fails?**  
A: Defaults to `"en"` (English). Can be manually corrected.

**Q: Does this cost extra in Pinecone?**  
A: No. Metadata is included in existing vectors. No extra cost.

---

## Next Steps

1. **Run migration**: `python migrate-add-language-tag.py`
2. **Test search**: `python agent_search.py`
3. **Update agent**: Import `search_with_language_filter`
4. **Deploy**: New ingestions will auto-detect language
