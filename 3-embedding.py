"""
3-embedding.py
-----------------
This script was historically using `docling` and a complex pipeline
but is currently non-functional and left broken. To avoid confusion
we provide a small wrapper that delegates to the working simple
embedding pipeline: `3-embedding-simple.py`.

Run this file to execute the simple pipeline instead.
"""

import subprocess
import sys

print("3-embedding.py is deprecated. Running 3-embedding-simple.py instead...")
try:
    subprocess.run([sys.executable, "3-embedding-simple.py"], check=True)
except subprocess.CalledProcessError as e:
    print(f"Embedded script failed: {e}")
    raise
