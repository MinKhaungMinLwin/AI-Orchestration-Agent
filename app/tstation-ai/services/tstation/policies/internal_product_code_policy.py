"""Policy helpers for preventing internal product identifier exposure."""

from __future__ import annotations

import re


_STANDALONE_GOODS_NO_RE = re.compile(r"\bG\d{6,}\b")
_EMPTY_PARENS_RE = re.compile(r"\(\s*\)")
_EXTRA_SPACES_RE = re.compile(r"[ \t]{2,}")


def sanitize_internal_product_codes(text: str) -> str:
    """Remove only obvious internal goods_no code tokens from final user-visible text."""

    if not text:
        return text
    sanitized = _STANDALONE_GOODS_NO_RE.sub("", text)
    sanitized = _EMPTY_PARENS_RE.sub("", sanitized)
    sanitized = _EXTRA_SPACES_RE.sub(" ", sanitized)
    lines = [line.strip() for line in sanitized.splitlines()]
    return "\n".join(line for line in lines if line)
