import streamlit as st
import lancedb
from mistralai import Mistral
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize Mistral client
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))


# Initialize LanceDB connection
@st.cache_resource
def init_db():
    """Initialize database connection.

    Returns:
        LanceDB table object
    """
    db = lancedb.connect("data/lancedb")
    return db.open_table("pregnancy_guide")  # matches 3-embedding-simple.py


def get_context(query: str, table, num_results: int = 5) -> str:
    """Search the database for relevant context.

    Args:
        query: User's question
        table: LanceDB table object
        num_results: Number of results to return

    Returns:
        str: Concatenated context from relevant chunks with source information
    """
    results = table.search(query).limit(num_results).to_pandas()
    contexts = []

    for _, row in results.iterrows():
        # 3-embedding-simple.py stores flat columns: source, title, chunk_index
        source = row.get("source", "")
        title  = row.get("title", "Untitled section")

        citation = f"\nSource: {source}"
        if title:
            citation += f"\nTitle: {title}"

        contexts.append(f"{row['text']}{citation}")

    return "\n\n".join(contexts)


def get_chat_response(messages, context: str) -> str:
    """Get streaming response from Mistral API.

    Args:
        messages: Chat history
        context: Retrieved context from database

    Returns:
        str: Model's response
    """
    system_prompt = f"""You are a helpful pregnancy health assistant that answers questions
based on the provided context. Use only the information from the context to answer questions.
If you're unsure or the context doesn't contain the relevant information, say so clearly.

Context:
{context}
"""

    messages_with_context = [{"role": "system", "content": system_prompt}, *messages]

    stream = client.chat.stream(
        model="mistral-large-latest",
        messages=messages_with_context,
        temperature=0.7,
    )

    # Stream the response token by token
    response_text = ""
    placeholder = st.empty()
    for chunk in stream:
        delta = chunk.data.choices[0].delta.content or ""
        response_text += delta
        placeholder.markdown(response_text + "▌")
    placeholder.markdown(response_text)
    return response_text


# ── Streamlit UI ───────────────────────────────────────────────

st.title("🤰 Pregnancy Health Assistant")
st.caption("Powered by NHS & MedlinePlus · Mistral AI · LanceDB")

if "messages" not in st.session_state:
    st.session_state.messages = []

table = init_db()

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ask about pregnancy nutrition, diet, vitamins…"):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.status("Searching knowledge base…", expanded=False):
        context = get_context(prompt, table)

        st.markdown("""
            <style>
            .search-result { margin:10px 0; padding:10px; border-radius:4px; background:#f0f2f6; }
            .search-result summary { cursor:pointer; color:#0f52ba; font-weight:500; }
            .search-result summary:hover { color:#1e90ff; }
            .meta { font-size:0.9em; color:#666; font-style:italic; }
            </style>
        """, unsafe_allow_html=True)

        st.write("Found relevant sections:")
        for chunk in context.split("\n\n"):
            parts = chunk.split("\n")
            text = parts[0]
            meta = {
                line.split(": ", 1)[0]: line.split(": ", 1)[1]
                for line in parts[1:]
                if ": " in line
            }
            source = meta.get("Source", "Unknown source")
            title  = meta.get("Title", "Untitled section")
            st.markdown(f"""
                <div class="search-result">
                    <details>
                        <summary>{source}</summary>
                        <div class="meta">Section: {title}</div>
                        <div style="margin-top:8px;">{text}</div>
                    </details>
                </div>
            """, unsafe_allow_html=True)

    with st.chat_message("assistant"):
        response = get_chat_response(st.session_state.messages, context)

    st.session_state.messages.append({"role": "assistant", "content": response})