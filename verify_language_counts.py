import os
from collections import Counter
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
index = pc.Index(name=os.getenv('PINECONE_INDEX', 'pregnancy-knowledge'), host=os.getenv('PINECONE_HOST'))
NAMESPACE = 'workspace'

counter = Counter()
checked = 0
for page in index.list(namespace=NAMESPACE):
    ids = [item.id for item in page.vectors]
    if not ids:
        continue
    resp = index.fetch(ids=ids, namespace=NAMESPACE)
    for vec in resp.get('vectors', {}).values():
        md = vec.get('metadata', {}) or {}
        counter[md.get('language', 'MISSING')] += 1
        checked += 1

print('checked', checked)
for lang, count in counter.most_common():
    print(f'{lang}: {count}')
