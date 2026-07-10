import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"
PRIMARY_FAQ_FILE = _DATA_DIR / "faq_data.json"
LOCAL_FAQ_FILE = _DATA_DIR / "local_faq.json"

# `metadata.source` values. Every Qdrant point carries one, and it decides who
# is allowed to delete it during a sync (see `_run_incremental_sync`).
PRIMARY_FAQ_SOURCE = "faq_data"
LOCAL_FAQ_SOURCE = "local_faq"
ORACLE_FAQ_SOURCE = "tstation-be"

# The two hand-edited files. Only a sync that reconciles these files may delete
# their points; the periodic Oracle fetch must never touch them.
FILE_FAQ_SOURCES = frozenset({PRIMARY_FAQ_SOURCE, LOCAL_FAQ_SOURCE})


def _load_json_array(path: Path, source: str) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"FAQ dataset must be a JSON array: {path}")

    docs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # Stamp provenance so the sync can tell file-owned points from Oracle ones.
        metadata = dict(item.get("metadata") or {})
        metadata.setdefault("source", source)
        docs.append({**item, "metadata": metadata})

    logger.info("[faq_dataset] Loaded %d document(s) from %s", len(docs), path.name)
    return docs


def merge_faq_documents(base_documents: list[dict], overlay_documents: list[dict]) -> list[dict]:
    """Merge overlay FAQ documents onto the base set, preserving order.

    Base documents keep their original order. Overlay documents are appended,
    or replace a base document when the same `id` is present.
    """
    merged: list[dict] = []
    index_by_id: dict[str, int] = {}

    for doc in base_documents:
        doc_id = str(doc.get("id"))
        index_by_id[doc_id] = len(merged)
        merged.append(doc)

    for doc in overlay_documents:
        doc_id = str(doc.get("id"))
        existing_index = index_by_id.get(doc_id)
        if existing_index is None:
            index_by_id[doc_id] = len(merged)
            merged.append(doc)
        else:
            merged[existing_index] = doc

    return merged


def load_file_faq_documents() -> list[dict]:
    """Both hand-edited FAQ files, merged by `id` (local_faq wins on collision)."""
    base_documents = _load_json_array(PRIMARY_FAQ_FILE, PRIMARY_FAQ_SOURCE)
    overlay_documents = _load_json_array(LOCAL_FAQ_FILE, LOCAL_FAQ_SOURCE)
    merged = merge_faq_documents(base_documents, overlay_documents)
    logger.info(
        "[faq_dataset] File FAQ documents: %s=%d %s=%d merged=%d",
        PRIMARY_FAQ_SOURCE,
        len(base_documents),
        LOCAL_FAQ_SOURCE,
        len(overlay_documents),
        len(merged),
    )
    return merged


def apply_file_overlays(base_documents: list[dict]) -> list[dict]:
    """Layer both FAQ files on top of `base_documents` (typically the Oracle set).

    Called from every ingestion path, so the file-backed FAQs are always part of
    the incoming document set — that is what keeps a sync from deleting them.
    """
    file_documents = load_file_faq_documents()
    merged = merge_faq_documents(base_documents, file_documents)
    logger.info(
        "[faq_dataset] Applied file overlays: base=%d files=%d merged=%d",
        len(base_documents),
        len(file_documents),
        len(merged),
    )
    return merged
