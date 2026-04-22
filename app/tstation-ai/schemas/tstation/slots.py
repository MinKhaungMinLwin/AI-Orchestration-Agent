import re
import logging
from typing import ClassVar, Literal, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# Unfulfilled user intent carried across turns until explicitly fulfilled by a matching tool call.
# "recommend" is the default/implicit intent and is intentionally NOT stored as a pending intent —
# only actionable transactional intents are tracked here.
PendingIntent = Literal["price", "stock", "order"]


class ConversationSlots(BaseModel):
    """Conversation slots for tracking confirmed customer information across turns."""

    tire_size: Optional[str] = None      # e.g. "225/45R17"
    tire_model: Optional[str] = None     # e.g. "벤투스 S2"
    goods_no: Optional[str] = None       # e.g. "G000000314254"
    ord_qty: Optional[int] = None        # e.g. 4
    shop_id: Optional[str] = None        # store code
    shop_name: Optional[str] = None      # e.g. "한남점"
    car_model: Optional[str] = None      # e.g. "쏘나타"
    pending_intent: Optional[PendingIntent] = None  # e.g. "price" — carried across turns, cleared by Coordinator when a matching tool runs.

    # Slot dependency: when a key changes, its dependent slots are reset to None
    DEPENDENT_RESETS: ClassVar[dict[str, list[str]]] = {
        "tire_model": ["goods_no"],
        "tire_size": ["goods_no"],
        "goods_no": ["tire_model", "tire_size"],
        "shop_name": ["shop_id"],
        "car_model": ["tire_size", "goods_no"],
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

    # Intent patterns. Order = priority: first match wins when a single user turn
    # mentions multiple intents (e.g., "가격이랑 재고" → price wins).
    # "order" is listed last because it's the most commitment-heavy and should only
    # be inferred from strong signals ("주문", "구매", "사고 싶어", "사려고", "살래").
    # Stock pattern is intentionally narrow: only unambiguous inventory terms (재고/입고)
    # qualify. Generic "있어?/있나요" is ambiguous ("이 상품 있어요?" vs "조용한 타이어 있어요?")
    # and was dropped to avoid false positives on pure recommendation turns.
    # Price pattern uses `얼마(?!나)` to avoid matching `얼마나` (degree adverb used in
    # stock/time questions like "재고 얼마나 있어요?" / "얼마나 걸려요?").
    _INTENT_PATTERNS: ClassVar[list[tuple[re.Pattern, "PendingIntent"]]] = [
        (re.compile(r"가격|얼마(?!나)|비용|총액|금액|할인된?\s*가격|할인가"), "price"),
        (re.compile(r"재고|입고"), "stock"),
        (re.compile(r"주문|구매|사고\s*싶|사려고|살래"), "order"),
    ]

    # Recommend patterns — when the user asks for a fresh recommendation,
    # any stale transactional pending_intent from earlier turns should be cleared,
    # because the user is explicitly switching back to discovery.
    _RECOMMEND_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"추천|골라줘|알아서|뭐가\s*좋|어떤\s*게\s*좋|괜찮은\s*거"),
    ]

    def merge(self, new_slots: "ConversationSlots") -> "ConversationSlots":
        """Merge new slots into existing slots with dependency reset logic.

        - Only non-None new values are applied.
        - If a value changes, dependent slots are reset to None.
        - Tracks which fields were reset by dependency for protection.
        """
        merged = self.model_copy()
        reset_fields = set(getattr(merged, "_reset_fields", set()))

        for field, new_val in new_slots.model_dump().items():
            if new_val is None:
                continue
            old_val = getattr(merged, field)

            # Value changed -> reset dependent slots
            if old_val is not None and old_val != new_val:
                for dep in self.DEPENDENT_RESETS.get(field, []):
                    logger.info(f"[SLOTS] {field} changed ({old_val} -> {new_val}), resetting {dep}")
                    setattr(merged, dep, None)
                    reset_fields.add(dep)

            setattr(merged, field, new_val)

        # Store reset fields for merge_fill_only to reference
        object.__setattr__(merged, "_reset_fields", reset_fields)
        return merged

    def merge_fill_only(
        self,
        new_slots: "ConversationSlots",
        overwrite_fields: set[str] | None = None,
    ) -> "ConversationSlots":
        """Merge new slots into existing slots, but ONLY fill None fields.

        - Does NOT overwrite existing non-None values.
        - Does NOT fill fields that were reset by dependency in a prior merge step.
        - Fields in overwrite_fields may overwrite if they are explicitly re-stated
          in the latest user turn.
        Used for LLM-extracted slots to prevent overwriting explicit user values.
        """
        merged = self.model_copy()
        reset_fields = getattr(merged, "_reset_fields", set())
        overwrite_fields = overwrite_fields or set()

        for field, new_val in new_slots.model_dump().items():
            if new_val is None:
                continue
            old_val = getattr(merged, field)

            if field in overwrite_fields:
                if old_val is not None and old_val != new_val:
                    for dep in self.DEPENDENT_RESETS.get(field, []):
                        logger.info(
                            f"[SLOTS] {field} explicitly changed in latest turn "
                            f"({old_val} -> {new_val}), resetting {dep}"
                        )
                        setattr(merged, dep, None)
                        reset_fields.add(dep)

                setattr(merged, field, new_val)
                continue

            # Skip if already has a value
            if old_val is not None:
                continue

            # Skip if this field was reset by dependency (protect reset)
            if field in reset_fields:
                logger.info(f"[SLOTS] Skipping LLM fill for {field} (was dependency-reset)")
                continue

            setattr(merged, field, new_val)

        object.__setattr__(merged, "_reset_fields", reset_fields)
        return merged

    @classmethod
    def extract_from_user_text(cls, user_text: str) -> "ConversationSlots":
        """Extract slot values from user message text using regex patterns.

        Extracts: tire_size, goods_no, ord_qty, pending_intent.
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

        # Intent: first matching pattern wins. Only set if a transactional keyword
        # is found — a pure recommendation turn leaves pending_intent untouched
        # so that prior-turn intents are preserved (see merge() logic).
        # If the user explicitly asks for a recommendation, callers should instead
        # clear pending_intent via has_recommend_intent() since switching back to
        # discovery supersedes any stale transactional intent.
        for pattern, intent_value in cls._INTENT_PATTERNS:
            if pattern.search(user_text):
                slots.pending_intent = intent_value
                break

        return slots

    @classmethod
    def has_recommend_intent(cls, user_text: str) -> bool:
        """Return True when the user turn explicitly asks for a recommendation.

        Used by Coordinator to clear any stale transactional `pending_intent`
        when the user is clearly switching back to discovery.
        """
        return any(pattern.search(user_text) for pattern in cls._RECOMMEND_PATTERNS)

    def to_prompt_context(self) -> str:
        """Format slots as a system prompt context string for agent injection.

        Emits up to two blocks:
        - [확인된 고객 정보] — confirmed ENTITY slots only (tire_size, goods_no, etc.).
          Carries the "do not re-ask; use tools for missing fields" instruction.
        - [사용자의 진행 중인 요청] — pending_intent, emitted as an independent hint.
          Does NOT carry the "do not re-ask" instruction, because intent alone is not
          confirmed entity data and an agent may still need to clarify product/store.
        Returns empty string when no slot is set.
        """
        entity_label_map = {
            "tire_size": "타이어 사이즈",
            "tire_model": "타이어 모델",
            "goods_no": "상품번호",
            "ord_qty": "수량",
            "shop_id": "매장코드",
            "shop_name": "매장명",
            "car_model": "차량 모델",
        }

        # Map pending_intent enum value → Korean label displayed in the prompt.
        intent_label_map = {
            "price": "가격 조회",
            "stock": "재고 확인",
            "order": "주문 진행",
        }

        entity_lines = []
        for field, label in entity_label_map.items():
            val = getattr(self, field)
            if val is not None:
                entity_lines.append(f"- {label}: {val}")

        blocks: list[str] = []

        if entity_lines:
            blocks.append(
                "\n".join([
                    "[확인된 고객 정보 - 이 정보는 다시 묻지 마세요]",
                    *entity_lines,
                    "[위 정보가 없는 항목은 tool을 호출하여 확인하세요. 유저에게 묻지 마세요.]",
                ])
            )

        if self.pending_intent is not None:
            intent_ko = intent_label_map.get(self.pending_intent, self.pending_intent)
            blocks.append(
                f"[사용자의 진행 중인 요청: {intent_ko}]\n"
                f"(이전 턴에서 사용자가 요청한 작업이며 아직 완료되지 않았습니다. "
                f"상품·매장 등 필요한 정보가 확정되어 있으면 해당 flow로 진행하고, "
                f"누락된 정보가 있으면 먼저 확인·선택 단계를 거쳐도 됩니다.)"
            )

        return "\n\n".join(blocks)

    def has_any(self) -> bool:
        """Return True if at least one slot is filled."""
        return any(v is not None for v in self.model_dump().values())
