"""Shared text matchers for policy-sensitive routing and response guards."""

from __future__ import annotations

import re

_CARD_CANCEL_SCOPE_RE = re.compile(
    r"카드사|카드|결제\s*수단|결제|환불|승인\s*취소|승인취소|취소\s*완료",
    re.IGNORECASE,
)
_CARD_CANCEL_ACTION_RE = re.compile(
    r"환불|승인\s*취소|승인취소|결제\s*취소|주문\s*취소|취소\s*완료|취소",
    re.IGNORECASE,
)
_CARD_CANCEL_TIMING_RE = re.compile(
    r"언제|며칠|얼마나|반영|걸려|소요|기간|시간",
    re.IGNORECASE,
)


def is_general_card_cancel_timing_policy_query(text: str) -> bool:
    """Return True only for refund/card-cancel timing questions.

    This deliberately avoids broad card-company/payment matches such as
    installments, discounts, or generic payment errors.
    """

    query = text or ""
    return bool(
        _CARD_CANCEL_SCOPE_RE.search(query)
        and _CARD_CANCEL_ACTION_RE.search(query)
        and _CARD_CANCEL_TIMING_RE.search(query)
    )
