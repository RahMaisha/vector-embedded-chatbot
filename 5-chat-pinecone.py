import os
import time
import requests
import streamlit as st
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

# ── Helpers ────────────────────────────────────────────────────

def embed_query(text: str) -> list:
    """Embed a query using Mistral API directly (no SDK)."""
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


def get_context(query: str, top_k: int = 5, language: str = None) -> list:
    """
    Search Pinecone for relevant chunks.
    
    Args:
        query: Search query text
        top_k: Number of results to return
        language: Optional language filter (e.g., "en", "ben")
    """
    query_embedding = embed_query(query)
    
    # Build filter for language if specified
    filter_dict = None
    if language:
        filter_dict = {"language": {"$eq": language}}
    
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        namespace=NAMESPACE,
        include_metadata=True,
        filter=filter_dict
    )
    return results.matches


def chat(query: str, context_matches: list) -> str:
    """Generate answer using Mistral chat API."""
    # Build context string with source titles
    context_parts = []
    for match in context_matches:
        title = match.metadata.get("title", "Unknown source")
        text  = match.metadata.get("text", "")
        url   = match.metadata.get("url", "")
        context_parts.append(f"[{title}]\n{text}\nSource: {url}")
    context = "\n\n---\n\n".join(context_parts)

    system_prompt = """You are a helpful pregnancy health assistant. 
Answer questions based only on the provided context.
Always mention the source title when referencing information.
If the context doesn't contain the answer, say so politely."""

    resp = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "mistral-large-latest",
            "messages": [
                {"role": "system", "content": f"{system_prompt}\n\nContext:\n{context}"},
                {"role": "user",   "content": query},
            ],
            "temperature": 0.3,
            "max_tokens": 600,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# ── Streamlit UI ───────────────────────────────────────────────

st.set_page_config(page_title="🤰 Pregnancy Assistant", page_icon="🤰")
st.title("🤰 Pregnancy Knowledge Assistant")
st.caption("Powered by NHS + MedlinePlus • Mistral AI • Pinecone")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask about pregnancy nutrition, diet, vitamins..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching knowledge base..."):
            try:
                matches = get_context(prompt)

                # Show sources in expander
                with st.expander(f"📚 {len(matches)} sources found"):
                    for match in matches:
                        title = match.metadata.get("title", "Unknown")
                        url   = match.metadata.get("url", "")
                        score = match.score
                        st.markdown(f"**{title}**  \n🔗 {url}  \n📊 Relevance: `{score:.2f}`")
                        st.markdown(f"> {match.metadata.get('text', '')[:200]}...")
                        st.divider()

                response = chat(prompt, matches)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

            except Exception as e:
                st.error(f"Error: {e}")