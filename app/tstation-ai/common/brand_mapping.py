"""
Brand name normalization for store search.

Maps English brand names to their official Korean equivalents.
This is applied BEFORE the LLM processes the input to prevent hallucination.

Rules:
- Normalize user input to Korean brand names
- Handle common variants and misspellings
- If no match found, return original input (fuzzy search/embedding handles it)
- Never let LLM guess brand names — use this mapping only
"""

# Brand mappings: English variants → Official Korean name
BRAND_MAPPING = {
    # The Tire Shop variants
    "the tire shop": "더타이어샵",
    "tire shop": "더타이어샵",
    "tireshop": "더타이어샵",
    "the tire": "더타이어샵",
    "tts": "더타이어샵",
    "the ts": "더타이어샵",
    "the tire sh": "더타이어샵",
    "더타이": "더타이어샵",

    # T-Station variants
    "the t-station": "티스테이션",
    "the t station": "티스테이션",
    "t-station": "티스테이션",
    "t station": "티스테이션",
    "tstation": "티스테이션",
    "t-st": "티스테이션",
    "티스테": "티스테이션",

    # All My T variants
    "all my t": "올마이티",
    "allmyt": "올마이티",
    "allmy-t": "올마이티",
    "all-my-t": "올마이티",

    # Add more brands as needed
}


def normalize_brand_name(user_input: str) -> str:
    """
    Normalize English brand name to Korean equivalent.

    Args:
        user_input (str): User-provided brand name (can be English or Korean).

    Returns:
        str: Normalized Korean brand name, or original input if no match found.

    Example:
        >>> normalize_brand_name("The Tire Shop")
        "더타이어샵"

        >>> normalize_brand_name("T-Station")
        "티스테이션"

        >>> normalize_brand_name("강남 매장")
        "강남 매장"  # Already Korean, return as-is

        >>> normalize_brand_name("unknown brand")
        "unknown brand"  # No mapping found, return original
    """
    if not user_input or not isinstance(user_input, str):
        return user_input

    # Normalize to lowercase for comparison
    lower_input = user_input.lower().strip()

    # Check for exact matches first
    if lower_input in BRAND_MAPPING:
        return BRAND_MAPPING[lower_input]

    # Check for partial matches (substring search)
    for key, korean in BRAND_MAPPING.items():
        if key in lower_input:
            return korean

    # No match found — return original input
    # (fuzzy/embedding search can handle it)
    return user_input


def is_likely_english_brand(text: str) -> bool:
    """
    Check if text appears to be an English brand name.

    Helps identify when brand normalization should be applied.

    Args:
        text (str): Text to check.

    Returns:
        bool: True if likely English brand name.
    """
    if not text:
        return False

    lower_text = text.lower().strip()

    # Check if it matches any known English variants
    for key in BRAND_MAPPING.keys():
        if key in lower_text:
            return True

    # Check if it contains English words commonly used in brand names
    english_keywords = ["shop", "station", "store", "tire", "the", "all", "my"]
    return any(kw in lower_text for kw in english_keywords)
