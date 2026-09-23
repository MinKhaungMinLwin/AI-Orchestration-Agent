"""
Inspect Qdrant FAQ collection: schema, indexes, and sample points.
Run from app/tstation-ai/:
    uv run python scripts/inspect_qdrant.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

from qdrant_client import QdrantClient

HOST = os.getenv("QDRANT_HOST", "localhost")
PORT = int(os.getenv("QDRANT_PORT", "6333"))
API_KEY = os.getenv("QDRANT_API_KEY") or None
COLLECTION = os.getenv("QDRANT_COLLECTION_FAQ", "faq_documents")

client = QdrantClient(host=HOST, port=PORT, api_key=API_KEY)


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


# 1. All collections
section("Collections")
for c in client.get_collections().collections:
    print(f"  {c.name}")

# 2. Aliases
section("Aliases")
for a in client.get_aliases().aliases:
    print(f"  {a.alias_name} → {a.collection_name}")

# 3. Resolve target collection (alias or direct)
target = COLLECTION
for a in client.get_aliases().aliases:
    if a.alias_name == COLLECTION:
        target = a.collection_name
        print(f"\n  '{COLLECTION}' is an alias → physical collection: {target}")
        break

# 4. Collection info
section(f"Collection Info: {target}")
info = client.get_collection(target)
print(f"  points_count   : {info.points_count}")
print(f"  status         : {info.status}")
print(f"  vectors_config : {list(info.config.params.vectors.keys()) if hasattr(info.config.params.vectors, 'keys') else info.config.params.vectors}")

# 5. Payload indexes
section("Payload Indexes (for keyword/text search)")
schema = info.payload_schema
if schema:
    for field, idx in schema.items():
        print(f"  {field}: {idx}")
else:
    print("  (none — no payload indexes configured)")

# 6. Sample points
section("Sample Points (first 3)")
points, _ = client.scroll(target, limit=3, with_vectors=False, with_payload=True)
for p in points:
    payload = p.payload or {}
    print(f"\n  ID      : {p.id}")
    print(f"  Fields  : {list(payload.keys())}")
    print(f"  question: {str(payload.get('question', ''))[:80]}")
    print(f"  answer  : {str(payload.get('answer', ''))[:80]}")
    meta = payload.get("metadata", {})
    print(f"  metadata: {json.dumps(meta, ensure_ascii=False)[:120]}")
