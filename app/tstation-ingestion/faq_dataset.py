import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"
PRIMARY_FAQ_FILE = _DATA_DIR / "faq_data.json"
LOCAL_FAQ_FILE = _DATA_DIR / "local_faq.json"


def _load_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"FAQ dataset must be a JSON array: {path}")
    docs = [item for item in data if isinstance(item, dict)]
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


def load_combined_faq_documents(*, include_local_overlay: bool = True) -> list[dict]:
    base_documents = _load_json_array(PRIMARY_FAQ_FILE)
    if not include_local_overlay:
        return base_documents

    overlay_documents = _load_json_array(LOCAL_FAQ_FILE)
    merged = merge_faq_documents(base_documents, overlay_documents)
    logger.info(
        "[faq_dataset] Combined FAQ documents: base=%d overlay=%d merged=%d",
        len(base_documents),
        len(overlay_documents),
        len(merged),
    )
    return merged


def load_local_overlay_documents() -> list[dict]:
    return _load_json_array(LOCAL_FAQ_FILE)


def apply_local_overlay(base_documents: list[dict]) -> list[dict]:
    overlay_documents = load_local_overlay_documents()
    merged = merge_faq_documents(base_documents, overlay_documents)
    logger.info(
        "[faq_dataset] Applied local overlay: base=%d overlay=%d merged=%d",
        len(base_documents),
        len(overlay_documents),
        len(merged),
    )
    return merged
