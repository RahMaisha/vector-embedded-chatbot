"""
agent_search.py
━━━━━━━━━━━━━━━━
Search utility for agents with automatic language detection and filtering.

This module provides language-aware vector search for agents:
- Detects the language of the user's query
- Automatically filters vectors by matching language
- Provides fallback to all vectors if no matches found

Usage by agent:
  from agent_search import search_with_language_filter
  
  results = search_with_language_filter(
      query="Your question here",
      top_k=5,
      detect_user_language=True  # Auto-detect from query
  )
"""

import os
import time
import requests
from typing import List, Optional
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

# ── Clients ────────────────────────────────────────────────────
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(
    name=os.getenv("PINECONE_INDEX", "pregnancy-knowledge"),
    host=os.getenv("PINECONE_HOST")
)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NAMESPACE = "workspace"


def embed_query(text: str) -> list:
    """Embed a query using Mistral API."""
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.mistral.ai/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {MISTRAL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": "mistral-embed", "input": [text]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
            else:
                raise RuntimeError(f"Embedding failed: {e}")


def detect_query_language(query: str) -> str:
    """
    Detect language from query text.
    Simple heuristics based on character ranges:
      - Bengali script (U+0980–U+09FF)
      - Latin (a-z, A-Z)
    Returns: "ben" or "en"
    """
    # Count Bengali characters
    bengali_chars = sum(
        1 for c in query 
        if '\u0980' <= c <= '\u09FF'
    )
    
    # If >30% of text is Bengali characters, it's Bengali
    if bengali_chars > len(query) * 0.3:
        return "ben"
    
    return "en"


def search_with_language_filter(
    query: str,
    top_k: int = 5,
    detect_user_language: bool = True,
    explicit_language: Optional[str] = None,
    fallback_to_all: bool = True
) -> List[dict]:
    """
    Search vectors with automatic language detection and filtering.
    
    Args:
        query: User query text
        top_k: Number of results to return
        detect_user_language: Auto-detect language from query (default: True)
        explicit_language: Force search in specific language ("en", "ben", etc)
        fallback_to_all: If no results found for language, search all vectors (default: True)
    
    Returns:
        List of matching vectors with metadata
    """
    
    # Determine target language
    if explicit_language:
        target_language = explicit_language
        print(f"🔍 Searching in language: {target_language} (explicit)")
    elif detect_user_language:
        target_language = detect_query_language(query)
        print(f"🔍 Detected query language: {target_language}")
    else:
        target_language = None
    
    # Embed the query
    query_embedding = embed_query(query)
    
    # Build filter for language if specified
    filter_dict = None
    if target_language:
        filter_dict = {"language": {"$eq": target_language}}
    
    # Search Pinecone
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        namespace=NAMESPACE,
        include_metadata=True,
        filter=filter_dict
    )
    
    matches = results.matches if hasattr(results, 'matches') else results.get('matches', [])
    
    # Fallback: if no results and filter was applied, search all vectors
    if not matches and filter_dict and fallback_to_all:
        print(f"   ⚠ No results in {target_language}. Searching all languages...")
        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace=NAMESPACE,
            include_metadata=True
        )
        matches = results.matches if hasattr(results, 'matches') else results.get('matches', [])
    
    # Format results
    formatted_results = [
        {
            "id": match.id,
            "score": match.score,
            "text": match.metadata.get("text", ""),
            "title": match.metadata.get("title", "Unknown"),
            "url": match.metadata.get("url", ""),
            "language": match.metadata.get("language", "unknown"),
            "metadata": match.metadata
        }
        for match in matches
    ]
    
    return formatted_results


def search_all_languages(
    query: str,
    top_k: int = 5
) -> dict:
    """
    Search across all languages and return results grouped by language.
    Useful for multilingual queries or analytics.
    
    Returns:
        Dict with language as key and list of results as value
    """
    query_embedding = embed_query(query)
    
    # Search without filter to get all results
    results = index.query(
        vector=query_embedding,
        top_k=top_k * 3,  # Get more to ensure we have results per language
        namespace=NAMESPACE,
        include_metadata=True
    )
    
    matches = results.matches if hasattr(results, 'matches') else results.get('matches', [])
    
    # Group by language
    grouped = {}
    for match in matches:
        lang = match.metadata.get("language", "unknown")
        if lang not in grouped:
            grouped[lang] = []
        grouped[lang].append({
            "id": match.id,
            "score": match.score,
            "text": match.metadata.get("text", ""),
            "title": match.metadata.get("title", "Unknown"),
            "url": match.metadata.get("url", ""),
        })
    
    # Trim to top_k per language
    for lang in grouped:
        grouped[lang] = grouped[lang][:top_k]
    
    return grouped


# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test the search utilities
    print("=" * 70)
    print("AGENT SEARCH UTILITY TEST")
    print("=" * 70)
    
    # Test 1: English query
    print("\n1️⃣ English Query:")
    results = search_with_language_filter(
        "What should I eat during pregnancy?",
        top_k=3
    )
    print(f"   Found {len(results)} results")
    for r in results:
        print(f"     • {r['title']} (lang: {r['language']}, score: {r['score']:.3f})")
    
    # Test 2: Language detection
    print("\n2️⃣ Language Detection:")
    query_en = "pregnancy nutrition tips"
    query_ben = "গর্ভকালীন পুষ্টি"
    print(f"   '{query_en}' → {detect_query_language(query_en)}")
    print(f"   '{query_ben}' → {detect_query_language(query_ben)}")
    
    # Test 3: All languages
    print("\n3️⃣ Multi-language Results:")
    grouped = search_all_languages("nutrition", top_k=2)
    for lang, results in grouped.items():
        print(f"   Language: {lang}")
        for r in results:
            print(f"     • {r['title']} (score: {r['score']:.3f})")
    
    print("\n✅ Test complete!")
