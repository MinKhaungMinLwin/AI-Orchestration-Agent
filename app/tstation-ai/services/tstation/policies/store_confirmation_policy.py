"""Store confirmation prompt/reply parsing helpers."""
from __future__ import annotations

import re


STORE_CONFIRMATION_REPLY_RE = re.compile(
    r"^\s*(?:네|넵|예|응|맞아|맞아요|네\s*,?\s*맞아요)\s*$",
    re.IGNORECASE,
)
STORE_CONFIRMATION_PROMPT_RE = re.compile(
    r"'(?P<requested>[^']+)'\s*으로\s*검색한\s*결과\s*'(?P<candidate>[^']+)'\s*매장이\s*있는데\s*이\s*매장이\s*맞을까요\?",
    re.IGNORECASE,
)
STORE_REGION_SUGGESTION_PROMPT_RE = re.compile(
    r"'(?P<user_input>[^']+)'\s*으로\s*검색되는\s*매장이\s*없습니다\.\s*'(?P<region>[^']+)'\s*지역으로\s*검색해\s*드릴까요\?",
    re.IGNORECASE,
)


def is_store_confirmation_reply(user_text: str | None) -> bool:
    return bool(STORE_CONFIRMATION_REPLY_RE.match((user_text or "").strip()))


def is_store_confirmation_prompt(text: str | None) -> bool:
    return bool(STORE_CONFIRMATION_PROMPT_RE.search(text or ""))


def resolve_store_followup_from_quickreply_template(
    user_text: str,
    template_data: dict | None,
) -> tuple[str | None, str | None]:
    """Resolve confirmed store/region from deterministic quickReply metadata."""
    if not user_text or not isinstance(template_data, dict):
        return None, None

    target_template: dict | None = None
    if template_data.get("template") == "quickReply" and isinstance(template_data.get("data"), dict):
        target_template = template_data.get("data")
    elif isinstance(template_data.get("quickReplies"), list):
        target_template = template_data
    if not isinstance(target_template, dict):
        return None, None

    metadata = target_template.get("metadata")
    if not isinstance(metadata, dict):
        return None, None
    confirmation = metadata.get("storeConfirmation")
    if not isinstance(confirmation, dict):
        return None, None

    text = user_text.strip()
    normalized = re.sub(r"\s+", " ", text)
    is_affirmative = is_store_confirmation_reply(normalized)

    candidate_stores = confirmation.get("candidateStores")
    if isinstance(candidate_stores, list) and candidate_stores:
        if is_affirmative and len(candidate_stores) == 1:
            first = candidate_stores[0]
            if isinstance(first, dict):
                shop_name = str(first.get("shopName") or "").strip()
                if shop_name:
                    return shop_name, None
        for store in candidate_stores:
            if not isinstance(store, dict):
                continue
            shop_name = str(store.get("shopName") or "").strip()
            if shop_name and shop_name == normalized:
                return shop_name, None

    suggested_region = str(confirmation.get("suggestedRegion") or "").strip()
    if suggested_region and (
        is_affirmative
        or suggested_region == normalized
        or f"{suggested_region} 지역 검색" == normalized
        or f"네, {suggested_region} 지역으로 검색" == normalized
    ):
        return None, suggested_region

    region_candidates = confirmation.get("regionCandidates")
    if isinstance(region_candidates, list):
        for region in region_candidates:
            region_text = str(region or "").strip()
            if not region_text:
                continue
            if (
                region_text == normalized
                or f"{region_text} 지역 검색" == normalized
                or f"네, {region_text} 지역으로 검색" == normalized
            ):
                return None, region_text

    return None, None


def resolve_store_followup_from_messages(
    user_text: str,
    messages: list[dict],
) -> tuple[str | None, str | None]:
    """Fallback parser for confirmation prompts when template metadata is absent."""
    if not user_text or not messages or not is_store_confirmation_reply(user_text):
        return None, None

    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue

        store_match = STORE_CONFIRMATION_PROMPT_RE.search(content)
        if store_match:
            candidate = store_match.group("candidate").strip()
            if candidate:
                return candidate, None

        region_match = STORE_REGION_SUGGESTION_PROMPT_RE.search(content)
        if region_match:
            region = region_match.group("region").strip()
            if region:
                return None, region

    return None, None
