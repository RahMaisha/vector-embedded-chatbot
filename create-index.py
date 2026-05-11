from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv
import os, time

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

INDEX_NAME = os.getenv("PINECONE_INDEX", "pregnancy-knowledge")

# e5-large-v2 produces 1024-dimensional vectors
if INDEX_NAME not in [i.name for i in pc.list_indexes()]:
    print(f"Creating index '{INDEX_NAME}'...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=1024,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
    # Wait until ready
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        print("  waiting...")
        time.sleep(3)
    print(f"✓ Index '{INDEX_NAME}' created and ready!")
else:
    print(f"✓ Index '{INDEX_NAME}' already exists")