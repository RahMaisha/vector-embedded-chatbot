"""
migrate-add-language-tag.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Safely adds "language" field to all existing vectors in Pinecone.

How it works:
  1. List all vectors in the namespace
  2. Extract filename/URL from existing metadata
  3. Detect language using language_detector utility
  4. Upsert vectors with updated metadata (includes language)
  5. Supports resuming from interrupted runs via checkpoints

Usage:
  python migrate-add-language-tag.py
  # or with custom namespace
  python migrate-add-language-tag.py --namespace workspace
"""

import os
import json
import argparse
from typing import List, Dict
from pinecone import Pinecone
from dotenv import load_dotenv
from utils.language_detector import detect_language

load_dotenv()

# ── Config ─────────────────────────────────────────────────────
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(
    name=os.getenv("PINECONE_INDEX", "pregnancy-knowledge"),
    host=os.getenv("PINECONE_HOST")
)

CHECKPOINT_FILE = "migration_checkpoint.json"
UPSERT_BATCH = 100


def load_checkpoint() -> Dict:
    """Load migration progress checkpoint."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"processed": 0, "last_id": None, "total": 0}


def save_checkpoint(checkpoint: Dict):
    """Save migration progress checkpoint."""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f, indent=2)


def fetch_all_vectors(namespace: str) -> List[Dict]:
    """
    Fetch all vectors with metadata from Pinecone.
    Note: This uses list() API which returns a generator of pages.
    """
    print(f"🔄 Fetching all vectors from namespace: {namespace}")
    
    all_vectors = []
    
    try:
        for page in index.list(namespace=namespace):
            # The Pinecone SDK may return pages in varying shapes depending on version.
            # Handle common shapes robustly: page.vectors (objects), a list of ids, or dicts.
            ids = []

            # Case A: page has attribute 'vectors' (list of objects)
            vecs = getattr(page, 'vectors', None)
            if vecs:
                for item in vecs:
                    if hasattr(item, 'id'):
                        ids.append(item.id)
                    elif isinstance(item, dict) and item.get('id'):
                        ids.append(item.get('id'))
                    elif isinstance(item, str):
                        ids.append(item)
            else:
                # Case B: page might be a plain list of ids or dicts
                try:
                    for item in page:
                        if isinstance(item, str):
                            ids.append(item)
                        elif isinstance(item, dict) and item.get('id'):
                            ids.append(item.get('id'))
                except Exception:
                    pass

            if not ids:
                continue

            vectors = index.fetch(ids=ids, namespace=namespace)
            for vec_id, vec_data in vectors.get("vectors", {}).items():
                all_vectors.append({
                    "id": vec_id,
                    "values": vec_data.get("values", []),
                    "metadata": vec_data.get("metadata", {}) or {}
                })

            print(f"  ✓ Fetched {len(all_vectors)} vectors so far...")
    except Exception as e:
        print(f"  ⚠ Error fetching vectors: {e}")
    
    return all_vectors


def migrate_vectors(namespace: str, dry_run: bool = False):
    """Migrate all vectors to add language metadata."""
    
    print("=" * 70)
    print("MIGRATE VECTORS: ADD LANGUAGE TAG")
    print("=" * 70)
    
    checkpoint = load_checkpoint()
    print(f"\n📍 Checkpoint: {checkpoint['processed']} processed")
    
    # Fetch all vectors
    all_vectors = fetch_all_vectors(namespace)
    total = len(all_vectors)
    
    if total == 0:
        print("❌ No vectors found in namespace:", namespace)
        return
    
    print(f"\n📊 Total vectors to process: {total}")
    print(f"   Dry run: {dry_run}")
    
    # Process and upsert in batches
    updated_vectors = []
    updated_count = 0
    skipped_count = 0
    
    for idx, vec in enumerate(all_vectors, start=1):
        vec_id = vec["id"]
        metadata = vec["metadata"]
        
        # Skip if already has language tag (unless force is enabled)
        if "language" in metadata and metadata.get("language"):
            if not globals().get('FORCE_MIGRATION', False):
                skipped_count += 1
                continue
        
        # Detect language from filename, URL, or the chunk text itself
        filename = metadata.get("filename") or metadata.get("title", "")
        url = metadata.get("url", "")
        text = metadata.get("text", "")
        
        language = detect_language(filename=filename, url=url, text=text)
        
        # Add language to metadata
        metadata["language"] = language
        
        updated_vec = {
            "id": vec_id,
            "values": vec["values"],
            "metadata": metadata
        }
        updated_vectors.append(updated_vec)
        updated_count += 1
        
        # Upsert in batches
        if len(updated_vectors) >= UPSERT_BATCH or idx == total:
            if not dry_run:
                try:
                    index.upsert(vectors=updated_vectors, namespace=namespace)
                    print(f"  ✓ Upserted {len(updated_vectors)} vectors ({idx}/{total})")
                except Exception as e:
                    print(f"  ✗ Upsert failed: {e}")
                    return
            else:
                print(f"  [DRY RUN] Would upsert {len(updated_vectors)} vectors ({idx}/{total})")
            
            # Save checkpoint
            checkpoint["processed"] = idx
            checkpoint["last_id"] = vec_id
            checkpoint["total"] = total
            save_checkpoint(checkpoint)
            
            updated_vectors = []
    
    print("\n" + "=" * 70)
    print("✅ MIGRATION COMPLETE!")
    print("=" * 70)
    print(f"  Updated  : {updated_count} vectors")
    print(f"  Skipped  : {skipped_count} (already had language tag)")
    print(f"  Total    : {total} vectors")
    print(f"  Namespace: {namespace}")
    
    # Clean up checkpoint
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print(f"\n  ✓ Checkpoint cleared")


def main():
    parser = argparse.ArgumentParser(description="Add language tag to existing Pinecone vectors")
    parser.add_argument("--namespace", type=str, default="workspace", help="Pinecone namespace (default: workspace)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without upserting")
    parser.add_argument("--force", action="store_true", help="Overwrite existing language metadata for all vectors")
    
    args = parser.parse_args()
    
    # Expose force flag globally so the fetch loop can read it without changing many function signatures
    globals()['FORCE_MIGRATION'] = args.force
    migrate_vectors(namespace=args.namespace, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
