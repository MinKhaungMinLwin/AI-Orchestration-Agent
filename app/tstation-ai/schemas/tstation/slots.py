import re
import logging
from typing import ClassVar, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ConversationSlots(BaseModel):
    """Conversation slots for tracking confirmed customer information across turns."""

    tire_size: Optional[str] = None      # e.g. "225/45R17"
    tire_model: Optional[str] = None     # e.g. "벤투스 S2"
    goods_no: Optional[str] = None       # e.g. "G000000314254"
    ord_qty: Optional[int] = None        # e.g. 4
    shop_id: Optional[str] = None        # store code
    shop_name: Optional[str] = None      # e.g. "한남점"
    car_model: Optional[str] = None      # e.g. "쏘나타"

    # Slot dependency: when a key changes, its dependent slots are reset to None
    DEPENDENT_RESETS: ClassVar[dict[str, list[str]]] = {
        "tire_model": ["goods_no"],
        "tire_size": ["goods_no"],
        "goods_no": ["tire_model", "tire_size"],
        "shop_name": ["shop_id"],
    }

    # Regex patterns for extracting slots from user messages
    # Tire size: "225/45R17", "225 45 17", "2254517"
    _TIRE_SIZE_PATTERNS: ClassVar[list[tuple[re.Pattern, str]]] = [
        # Standard format: 225/45R17
        (re.compile(r"(\d{3})/(\d{2})R(\d{2})"), "{0}/{1}R{2}"),
        # Flexible whitespace/separator: "225 45 17", "225 4517", "22545 17", "225/45/17"
        (re.compile(r"(?<!\d)(\d{3})[\s/]?(\d{2})[\s/]?(\d{2})(?!\d)"), "{0}/{1}R{2}"),
    ]
    _GOODS_NO_PATTERN: ClassVar[re.Pattern] = re.compile(r"G\d{9,}")
    _ORD_QTY_PATTERN: ClassVar[re.Pattern] = re.compile(r"(\d+)\s*개")

    def merge(self, new_slots: "ConversationSlots") -> "ConversationSlots":
        """Merge new slots into existing slots with dependency reset logic.

        - Only non-None new values are applied.
        - If a value changes, dependent slots are reset to None.
        """
        merged = self.model_copy()

        for field, new_val in new_slots.model_dump().items():
            if new_val is None:
                continue
            old_val = getattr(merged, field)

            # Value changed -> reset dependent slots
            if old_val is not None and old_val != new_val:
                for dep in self.DEPENDENT_RESETS.get(field, []):
                    logger.info(f"[SLOTS] {field} changed ({old_val} -> {new_val}), resetting {dep}")
                    setattr(merged, dep, None)

            setattr(merged, field, new_val)

        return merged

    @classmethod
    def extract_from_user_text(cls, user_text: str) -> "ConversationSlots":
        """Extract slot values from user message text using regex patterns.

        Only extracts: tire_size, goods_no, ord_qty.
        tire_model, shop_name, car_model require LLM extraction (handled by Router).
        """
        slots = cls()

        # Try tire size patterns in priority order (standard > space > concatenated)
        for pattern, fmt in cls._TIRE_SIZE_PATTERNS:
            tire_size_match = pattern.search(user_text)
            if tire_size_match:
                slots.tire_size = fmt.format(
                    tire_size_match.group(1),
                    tire_size_match.group(2),
                    tire_size_match.group(3),
                )
                break

        goods_no_match = cls._GOODS_NO_PATTERN.search(user_text)
        if goods_no_match:
            slots.goods_no = goods_no_match.group(0)

        qty_match = cls._ORD_QTY_PATTERN.search(user_text)
        if qty_match:
            slots.ord_qty = int(qty_match.group(1))

        return slots

    def to_prompt_context(self) -> str:
        """Format slots as a system prompt context string for agent injection."""
        label_map = {
            "tire_size": "타이어 사이즈",
            "tire_model": "타이어 모델",
            "goods_no": "상품번호",
            "ord_qty": "수량",
            "shop_id": "매장코드",
            "shop_name": "매장명",
            "car_model": "차량 모델",
        }

        confirmed = []
        missing = []
        for field, label in label_map.items():
            val = getattr(self, field)
            if val is not None:
                confirmed.append(f"- {label}: {val}")
            else:
                missing.append(f"- {label}")

        lines = []
        if confirmed:
            lines.append("[확인된 고객 정보 - 이 정보는 다시 묻지 마세요]")
            lines.extend(confirmed)
        if missing:
            lines.append("[미확인 정보 - 필요 시 자연스럽게 확인하세요]")
            lines.extend(missing)

        return "\n".join(lines)

    def has_any(self) -> bool:
        """Return True if at least one slot is filled."""
        return any(v is not None for v in self.model_dump().values())
