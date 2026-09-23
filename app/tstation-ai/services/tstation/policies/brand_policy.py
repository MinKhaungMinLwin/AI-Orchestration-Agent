"""Deterministic brand support policy for T-Station tire queries."""

from __future__ import annotations

from dataclasses import dataclass
import re


SUPPORTED_BRANDS: dict[str, str] = {
    "HK": "한국타이어",
    "LF": "라우펜",
    "MC": "미쉐린",
    "PI": "피렐리",
    "BS": "브리지스톤",
    "CT": "콘티넨탈",
    "GY": "굿이어",
}

SUPPORTED_BRAND_ALIASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("HK", "한국타이어", ("한국타이어", "한국", "hankook")),
    ("LF", "라우펜", ("라우펜", "laufenn")),
    ("MC", "미쉐린", ("미쉐린", "michelin")),
    ("PI", "피렐리", ("피렐리", "pirelli")),
    ("BS", "브리지스톤", ("브리지스톤", "브릿지스톤", "bridgestone")),
    ("CT", "콘티넨탈", ("콘티넨탈", "continental", "conti")),
    ("GY", "굿이어", ("굿이어", "goodyear")),
)

UNSUPPORTED_BRAND_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("금호", ("금호", "kumho")),
    ("넥센", ("넥센", "nexen")),
    ("던롭", ("던롭", "dunlop")),
    ("요코하마", ("요코하마", "yokohama")),
    ("토요", ("토요", "toyo")),
    ("맥시스", ("맥시스", "maxxis")),
    ("쿠퍼", ("쿠퍼", "cooper")),
    ("BFGoodrich", ("bfgoodrich", "bf goodrich", "비에프굿리치")),
    ("Falken", ("falken", "팔켄")),
    ("Vredestein", ("vredestein", "브레데슈타인")),
    ("Linglong", ("linglong", "링롱")),
    ("Sailun", ("sailun", "사일룬")),
)

_BRAND_AVAILABILITY_INQUIRY_RE = re.compile(
    r"취급|판매|팔아|파나|있어|있는지|구매|주문|재고|장착\s*가능|장착해|"
    r"추천|검색|찾아|가격|얼마|최저가|상품|타이어",
    re.IGNORECASE,
)
_STORE_CONTEXT_RE = re.compile(
    r"(?:티스테이션|더타이어샵)?\s*[가-힣A-Za-z0-9]+점|매장|지점",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BrandPolicyMatch:
    label: str
    aliases: tuple[str, ...]
    has_store_context: bool


def _alias_matches(text: str, alias: str) -> bool:
    if re.search(r"[A-Za-z]", alias):
        compact_text = re.sub(r"[\s\-_]+", "", text.casefold())
        compact_alias = re.sub(r"[\s\-_]+", "", alias.casefold())
        return compact_alias in compact_text
    for match in re.finditer(re.escape(alias), text):
        next_char = text[match.end(): match.end() + 1]
        if next_char in {"동", "로", "길", "역"}:
            continue
        return True
    return False


def supported_brand_match(text: str | None) -> tuple[str, str] | None:
    query = str(text or "")
    for brand_cd, label, aliases in SUPPORTED_BRAND_ALIASES:
        if any(_alias_matches(query, alias) for alias in aliases):
            return brand_cd, label
    return None


def unsupported_brand_policy_match(
    text: str | None,
    *,
    recent_context: str | None = None,
) -> BrandPolicyMatch | None:
    """Detect known tire brands that T-Station AI cannot search/recommend.

    Unknown words are intentionally ignored. A known unsupported brand only
    triggers when the current turn also looks like a tire availability/search
    question, so place names such as "금호동" do not get blocked by brand policy.
    """
    query = str(text or "").strip()
    if not query:
        return None
    if supported_brand_match(query):
        return None
    if not _BRAND_AVAILABILITY_INQUIRY_RE.search(query):
        return None

    matched: list[tuple[str, tuple[str, ...]]] = []
    for label, aliases in UNSUPPORTED_BRAND_ALIASES:
        if any(_alias_matches(query, alias) for alias in aliases):
            matched.append((label, aliases))

    if not matched:
        return None
    label = "·".join(dict.fromkeys(label for label, _aliases in matched))
    aliases = tuple(alias for _label, aliases in matched for alias in aliases)
    context = f"{query}\n{recent_context or ''}"
    return BrandPolicyMatch(
        label=label,
        aliases=aliases,
        has_store_context=bool(_STORE_CONTEXT_RE.search(context)),
    )
