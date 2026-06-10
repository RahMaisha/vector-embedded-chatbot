"""
Streamlit dashboard: Language tag overview for Pinecone index

Run:
    streamlit run language_dashboard.py

Features:
- Shows total vectors and counts per `language` metadata
- Displays sample vectors per language
- Allows export of CSV report
"""
import os
import time
import io
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_HOST = os.getenv("PINECONE_HOST")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "pregnancy-knowledge")
DEFAULT_NAMESPACE = "workspace"

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(name=PINECONE_INDEX, host=PINECONE_HOST)


def fetch_all_vectors(namespace: str = DEFAULT_NAMESPACE):
    """Fetch all vectors and return list of dicts with id and metadata."""
    vectors = []
    # index.list may return a dict (single page) or a generator (paged)
    resp = index.list(namespace=namespace)
    ids = []
    if hasattr(resp, "get"):
        ids = resp.get("vectors", [])
    else:
        for page in resp:
            ids.extend(page.get("vectors", []) or [])

    if not ids:
        return vectors

    # fetch in pages of up to 100
    for i in range(0, len(ids), 100):
        batch_ids = ids[i:i+100]
        fetched = index.fetch(ids=batch_ids, namespace=namespace)
        for vid, data in fetched.get("vectors", {}).items():
            vectors.append({
                "id": vid,
                **{k: v for k, v in data.get("metadata", {}).items()}
            })
    return vectors


st.set_page_config(page_title="Language Dashboard", layout="wide")
st.title("Vector Language Dashboard")

with st.sidebar:
    st.markdown("## Settings")
    namespace = st.text_input("Pinecone namespace", value=DEFAULT_NAMESPACE)
    refresh = st.button("Refresh data")

if "data" not in st.session_state or refresh:
    with st.spinner("Fetching vectors from Pinecone..."):
        vectors = fetch_all_vectors(namespace=namespace)
        df = pd.DataFrame(vectors)
        st.session_state.data = df
        st.success(f"Fetched {len(df)} vectors")
else:
    df = st.session_state.data

if df.empty:
    st.warning("No vectors found. Check namespace or index configuration in .env.")
else:
    # Language counts
    if "language" not in df.columns:
        st.error("No 'language' field present in vector metadata.")
    else:
        lang_counts = df["language"].fillna("unknown").value_counts()
        col1, col2 = st.columns([2,3])
        with col1:
            st.metric("Total vectors", len(df))
            st.bar_chart(lang_counts)
            st.write(lang_counts)
        with col2:
            st.markdown("### Sample vectors by language")
            lang = st.selectbox("Select language", options=list(lang_counts.index))
            sample = df[df["language"].fillna("unknown") == lang].head(50)
            st.dataframe(sample)

        # CSV export
        csv = df.to_csv(index=False)
        st.download_button("Download CSV report", data=csv, file_name="language_report.csv", mime="text/csv")

st.caption("Dashboard uses PINECONE_INDEX and PINECONE_HOST from .env")
