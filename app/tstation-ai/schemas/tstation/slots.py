from __future__ import annotations

import datetime
import logging
import re
from typing import Any, ClassVar, Literal, Mapping, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Unfulfilled user intent carried across turns until explicitly fulfilled by a matching tool call.
# "recommend" is the default/implicit intent and is intentionally NOT stored as a pending intent —
# only actionable transactional intents are tracked here.
# "reservation" covers 매장 방문 예약 (타이어 장착 외에 와이퍼/배터리/얼라인먼트/경정비 등
# 부가 서비스 예약 포함). Distinguished from "order" — "예약" 단독 발화는 서비스 방문이지
# 상품 주문이 아니다. template_mapper 가 isBookingFlow=true 분기 시 함께 본다.
PendingIntent = Literal["price", "stock", "order", "reservation", "quantity_benefit_comparison"]
AvailabilityIntent = Literal["today_install"]

# High-level user goal carried across the session. Drives both goal-aware prompt
# injection (so agents know the *destination*, not just the immediate turn) and
# the goal-based fast-path classifier (so the coordinator can route by next
# missing step instead of paying the LLM-classifier cost on every turn).
# Sticky: once detected, persists across turns until the user explicitly switches
# (handled by extract_from_user_text re-running on each turn).
GoalType = Literal[
    "product_recommend",
    "product_search",
    "store_with_stock",
    "store_finder",
    "price_inquiry",
    "place_order",
]


class RecommendationContext(BaseModel):
    """Typed recommendation-only context kept separate from durable common slots."""

    scenario: Optional[str] = None
    applied_rcmd_type: Optional[str] = None
    applied_vehicle_type: Optional[str] = None
    applied_season_nm: Optional[str] = None
    approximation: bool = False
    approximation_basis: Optional[str] = None
    source_text: Optional[str] = None
    fitment_source: Optional[str] = None
    tool_args_patch: Optional[dict[str, Any]] = None
    expected_tool_args: Optional[dict[str, Any]] = None
    scope: Optional[str] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | "RecommendationContext" | None) -> "RecommendationContext | None":
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        data = {key: item for key, item in dict(value).items() if item not in (None, "")}
        if "scenario" not in data and data.get("recommendation_scenario"):
            data["scenario"] = data.get("recommendation_scenario")
        return cls(**{key: item for key, item in data.items() if key in cls.model_fields})

    def to_policy_dict(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if self.scenario:
            data["recommendation_scenario"] = self.scenario
        return data


class ComparisonContext(BaseModel):
    """Typed comparison-only context preserved after deterministic compare answers."""

    product_names: list[str] = Field(default_factory=list)
    compare_metric: Optional[str] = None
    response_shape_key: Optional[str] = None
    comparison_followup_intent: Optional[str] = None
    source: Optional[str] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | "ComparisonContext" | None) -> "ComparisonContext | None":
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        data = {key: item for key, item in dict(value).items() if item not in (None, "")}
        product_names = data.get("product_names") or data.get("productNames")
        if isinstance(product_names, (tuple, list)):
            data["product_names"] = [str(name).strip() for name in product_names if str(name or "").strip()][:2]
        return cls(**{key: item for key, item in data.items() if key in cls.model_fields})

    def to_policy_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ConversationSlots(BaseModel):
    """Conversation slots for tracking confirmed customer information across turns."""

    tire_size: Optional[str] = None      # e.g. "225/45R17"
    tire_size_front: Optional[str] = None  # selected vehicle front tire size
    tire_size_rear: Optional[str] = None   # selected vehicle rear tire size
    tire_model: Optional[str] = None     # e.g. "벤투스 S2"
    goods_no: Optional[str] = None       # e.g. "G000000314254"
    ord_qty: Optional[int] = None        # e.g. 4
    shop_id: Optional[str] = None        # store code
    shop_name: Optional[str] = None      # e.g. "한남점"
    car_model: Optional[str] = None      # e.g. "쏘나타"
    car_no: Optional[str] = None         # e.g. "12가3456"
    car_lnc_cd: Optional[str] = None     # vehicle WCODE
    car_type: Optional[str] = None       # raw registered vehicle type, e.g. "SUV"
    vehicle_type: Optional[str] = None   # normalized recommendation filter, e.g. "suv"
    mbr_car_reg_seq: Optional[str] = None  # member car registration sequence
    pending_vehicle_lookup_car_no: Optional[str] = None  # unmatched plate awaiting owner name
    region: Optional[str] = None         # e.g. "분당" — region/area for store_finder goal
    availability_intent: Optional[AvailabilityIntent] = None  # e.g. "today_install"
    requested_cal_day: Optional[str] = None  # YYYYMMDD requested install/reservation date
    rsv_hour: Optional[str] = None       # HH from datepick selection for quick_order_tool
    # 결제금액(원). `get_final_price_tool` 결과 + `ord_qty` 로 산출되거나
    # `quick_order_tool` 결과의 정확한 금액으로 채워진다. 슬롯에 보존되면
    # LLM 이 컨텍스트만으로 단가·수량 곱셈을 추측해 hallucination 하지 않고
    # 결정적 값을 그대로 인용할 수 있다. (예: 할부 계산 질문)
    payment_amount: Optional[int] = None
    # Free-form user store-selection criteria captured on the originating turn
    # (e.g. "친절한 직원, 얼라인먼트, 워셔액 무료"). Sticky across slot-fill
    # turns so the agent can re-apply the criteria once the missing slot
    # (region/address) is satisfied. Cleared automatically when goal_type flips.
    user_preferences_text: Optional[str] = None
    pending_intent: Optional[PendingIntent] = None  # e.g. "price" — carried across turns, cleared by Coordinator when a matching tool runs.
    pending_product_name: Optional[str] = None  # product name waiting for a missing slot follow-up
    pending_quantity_options: Optional[list[int]] = None  # quantity comparison options, e.g. [2, 4]
    pending_required_slot: Optional[str] = None  # missing slot requested in the previous assistant turn
    goal_type: Optional[GoalType] = None  # e.g. "store_with_stock" — high-level destination, sticky across turns.
    recommendation_variants: Optional[list[dict[str, Any]]] = None
    recommendation_limit_per_variant: Optional[int] = None
    recommendation_source_text: Optional[str] = None
    recommendation_context: Optional[RecommendationContext] = None
    comparison_context: Optional[ComparisonContext] = None
    availability_context: Optional[dict[str, Any]] = None
    order_context: Optional[dict[str, Any]] = None
    quantity_comparison_context: Optional[dict[str, Any]] = None
    price_facts: Optional[dict[str, Any]] = None
    coupon_facts: Optional[dict[str, Any]] = None

    # Slot dependency: when a key changes, its dependent slots are reset to None
    DEPENDENT_RESETS: ClassVar[dict[str, list[str]]] = {
        "pending_product_name": ["goods_no", "payment_amount"],
        "tire_model": ["goods_no", "payment_amount"],
        "tire_size": ["goods_no", "payment_amount"],
        "tire_size_front": ["goods_no", "payment_amount"],
        "tire_size_rear": ["goods_no", "payment_amount"],
        "goods_no": ["tire_model", "tire_size", "payment_amount"],
        "ord_qty": ["payment_amount"],
        "shop_name": ["shop_id"],
        "car_model": [
            "car_no",
            "car_lnc_cd",
            "car_type",
            "vehicle_type",
            "mbr_car_reg_seq",
            "tire_size",
            "tire_size_front",
            "tire_size_rear",
            "goods_no",
            "payment_amount",
        ],
        "car_no": [
            "car_model",
            "car_lnc_cd",
            "car_type",
            "vehicle_type",
            "mbr_car_reg_seq",
            "tire_size",
            "tire_size_front",
            "tire_size_rear",
            "goods_no",
            "payment_amount",
        ],
        # When the goal flips, drop free-form store preferences (they are session-specific).
        # Region changes mean the user is searching a new area, not confirming the
        # previous store. Clear store identity so a stale shop_id cannot satisfy
        # the "매장 선택" step after a region-only follow-up like "성남은?".
        "goal_type": ["user_preferences_text"],
        "region": ["shop_id", "shop_name"],
    }
    RUNTIME_DEPENDENT_RESETS: ClassVar[dict[str, list[str]]] = {
        # Runtime product resolution is usually "same size, different model".
        # Keep tire_size so Discovery/Transaction can re-query the new SKU under
        # the user's active size, but never keep old product label or amount.
        "goods_no": ["tire_model", "payment_amount"],
        "pending_product_name": ["goods_no", "payment_amount"],
        "tire_model": ["goods_no", "payment_amount"],
        "tire_size": ["goods_no", "payment_amount"],
        "tire_size_front": ["goods_no", "payment_amount"],
        "tire_size_rear": ["goods_no", "payment_amount"],
        "ord_qty": ["payment_amount"],
        "shop_name": ["shop_id", "payment_amount"],
        "shop_id": ["payment_amount"],
        "region": ["shop_id", "shop_name"],
        "car_model": [
            "car_no",
            "car_lnc_cd",
            "car_type",
            "vehicle_type",
            "mbr_car_reg_seq",
            "tire_size",
            "tire_size_front",
            "tire_size_rear",
            "goods_no",
            "payment_amount",
        ],
        "car_no": [
            "car_model",
            "car_lnc_cd",
            "car_type",
            "vehicle_type",
            "mbr_car_reg_seq",
            "tire_size",
            "tire_size_front",
            "tire_size_rear",
            "goods_no",
            "payment_amount",
        ],
    }
    PRODUCT_IDENTITY_FIELDS: ClassVar[set[str]] = {
        "pending_product_name",
        "tire_model",
        "tire_size",
        "tire_size_front",
        "tire_size_rear",
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
    _SHOP_NAME_PATTERN: ClassVar[re.Pattern] = re.compile(r"([가-힣A-Za-z0-9]+(?:점|매장))")
    # "10개월"/"10개구" 처럼 "개" 뒤에 한글이 이어지는 경우 quantity 로 오추출되지 않도록
    # negative lookahead 로 차단. "4개", "4개 주세요", "4개." 는 정상 매칭.
    _ORD_QTY_PATTERN: ClassVar[re.Pattern] = re.compile(r"(\d+)\s*개(?![가-힣])")
    _TODAY_INSTALL_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"오늘\s*(?:바로\s*)?장착|오늘\s*서비스|오늘서비스|당일\s*(?:장착|서비스)|"
        r"오늘\s*가능|바로\s*장착|지금\s*장착|당장\s*장착",
        re.IGNORECASE,
    )
    _TODAY_DATE_PATTERN: ClassVar[re.Pattern] = re.compile(r"오늘|당일|지금|바로|당장", re.IGNORECASE)
    _RELATIVE_DATE_PATTERN: ClassVar[re.Pattern] = re.compile(r"내일|모레", re.IGNORECASE)
    _EXPLICIT_MD_DATE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일"
    )

    # Intent patterns. Order = priority: first match wins when a single user turn
    # mentions multiple intents (e.g., "가격이랑 재고" → price wins).
    # "order" is listed last because it's the most commitment-heavy and should only
    # be inferred from strong signals ("주문", "구매", "사고 싶어", "사려고", "살래",
    # "장착하고 싶어/장착할게/장착해줘" — 타이어 매장 장착은 commit-heavy 구매 의도).
    # Stock pattern covers: 재고/입고 (direct inventory) and 장착 가능 (tire-install
    # availability — implies stock at a store). The `\s*가능` tail is deliberate:
    #   - Narrows "장착" so mixed purchase turns like "주문해서 장착하고 싶어요" fall
    #     through to the `order` pattern instead of being captured as stock.
    #   - Avoids `장착료 / 장착비 / 공임` (price, not stock).
    # `방문` is intentionally NOT included: a store visit may be for battery/engine
    # oil/general maintenance, not tire installation — matching it as "stock" would
    # mis-route non-tire service questions through the tire inventory flow.
    # Price pattern uses `얼마(?!나)` to avoid matching `얼마나` (degree adverb used in
    # stock/time questions like "재고 얼마나 있어요?" / "얼마나 걸려요?").
    _INTENT_PATTERNS: ClassVar[list[tuple[re.Pattern, "PendingIntent"]]] = [
        (
            re.compile(
                r"가격|얼마(?!나)|비용|총액|금액|할인된?\s*가격|할인가|"
                r"스마트\s*페이|할부|분할\s*납부|월\s*납부|월\s*결제"
            ),
            "price",
        ),
        (re.compile(r"재고|입고|장착\s*가능"), "stock"),
        # 장착 의도 — 타이어 매장 장착은 commit-heavy 구매 의도다. "장착하고 싶어",
        # "장착하려고", "장착할래/장착할게", "장착해줘/장착해 주세요" 등 의도 동사
        # 결합 케이스만 매칭. 단순 "장착비/장착료/장착 공임" (price) 과 "장착 가능"
        # (stock) 은 위 두 패턴이 우선 매칭하므로 충돌 없음.
        (
            re.compile(
                r"주문|구매|사고\s*싶|사려고|살래|"
                r"장착하고\s*싶|장착하려|장착할래|장착할게|장착해\s*줘|장착해\s*주세요"
            ),
            "order",
        ),
        # 매장 방문 예약 — 와이퍼/배터리/얼라인먼트/경정비 등 부가 서비스 예약 포함.
        # "주문 예약" 같은 복합 발화는 위의 "order" 패턴이 먼저 매칭되어 reservation 으로
        # 떨어지지 않는다 (first-match-wins). 취소/변경 동사는 downstream 분류기·prompt
        # 가 별도 처리하므로 여기서는 broad match 로 두고 컨텍스트만 표시.
        (re.compile(r"예약"), "reservation"),
    ]

    # Recommend patterns — when the user asks for a fresh recommendation,
    # any stale transactional pending_intent from earlier turns should be cleared,
    # because the user is explicitly switching back to discovery.
    _RECOMMEND_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"추천|골라줘|알아서|뭐가\s*좋|어떤\s*게\s*좋|괜찮은\s*거"),
    ]

    # Store-finder patterns — turns where the user explicitly looks for a store
    # without a price/stock/order intent. Drives `store_finder` goal so the
    # coordinator routes through the goal-router (preserving preferences across
    # the region clarification turn) instead of running ad-hoc per-turn.
    # NOTE: Only fires when no transactional pending_intent is set (price/stock/
    # order takes priority via the elif chain in `extract_from_user_text`).
    _STORE_FINDER_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(
            r"매장|샵|지점|티스테이션|더타이어샵|올마이T|올마이티|"
            r"가까운\s*곳|근처(?:에)?\s*(?:매장|샵|지점)|"
            r"내\s*주변(?:에)?(?:\s*매장|\s*샵|\s*지점)?|"
            r"어디.*(?:매장|샵|지점)|(?:매장|샵|지점).*어디"
        ),
    ]

    # Soft preference hints — when present together with a store-finder turn,
    # capture the full user_text into `user_preferences_text` so the agent can
    # filter/rank stores against these criteria after the region slot is filled.
    # Kept narrow on purpose: a bland "근처 매장 알려줘" should NOT capture
    # preferences (no real criteria), so the next-turn region answer routes
    # through the default flow instead of dragging an empty preference block.
    _PREFERENCE_HINT_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(
            r"친절|여성|얼라인먼트|밸런스|워셔액|무료|깨끗|믿을|친근|편하|"
            r"잘\s*봐|꼼꼼|전문|특화|수입차|외제차|프리미엄|"
            r"평점|리뷰|평이?\s*좋|"
            r"발렛|대기실|커피|음료|와이파이|키즈|여성\s*전용|아이.*동반|"
            r"리프트|질소\s*충전|질소|라운지|휴게실|수유실|파우더룸|"
            r"청결|쾌적|분위기|숙련도|실력|정확도"
        ),
    ]

    # Region/area whitelist — Korean metro districts and frequently-mentioned
    # neighborhoods. Bounded by non-Hangul/Latin lookarounds so common
    # substrings ("동작 안 해") don't false-positive. Generic "[가-힣]+(구|동|시|...)"
    # fallbacks are intentionally NOT included here to avoid noisy matches;
    # the LLM prompt still handles unrecognized region names through the
    # existing get_store_list_tool(region_code=...) path.
    _REGION_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"(?<![가-힣A-Za-z0-9])"
        r"(?P<region>"
        # Seoul gu
        r"강남|강북|강동|강서|관악|광진|구로|금천|노원|도봉|동대문|동작|마포"
        r"|서대문|서초|성동|성북|송파|양천|영등포|용산|은평|종로|중랑"
        # Seoul districts/landmarks
        r"|서울|잠실|판교|역삼|논현|압구정|신사|청담|반포|방배|이태원|홍대|연남"
        r"|성수|왕십리|건대|선릉|삼성"
        # Gyeonggi
        r"|분당|수정|중원|수원|영통|성남|용인|기흥|수지|처인"
        r"|안양|만안|동안|고양|덕양|일산|파주|광명|부천|안산|단원|상록|시흥"
        r"|의왕|하남|김포|평택|안성|이천|여주|화성|동탄|오산|군포|의정부"
        r"|남양주|구리"
        # Incheon
        r"|인천|남동|연수|미추홀|부평|계양"
        # Busan / Daegu / Gwangju / Daejeon / Ulsan / Jeju
        r"|부산|해운대|수영|동래|연제|기장"
        r"|대구|수성|달서|달성"
        r"|광주|대전|유성|울산|울주|제주|서귀포"
        # Other major cities
        r"|춘천|강릉|원주|속초"
        r"|창원|마산|진주|통영|포항|경주|구미"
        r"|전주|군산|익산|목포|순천|광양|여수"
        r"|청주|충주|천안|아산"
        r")"
        # Trailing lookahead intentionally OMITTED so common Korean particles
        # (에/은/는/이/가/쪽/구/시/...) don't block legitimate matches.
        # Risk: "강남구청" matches "강남" — acceptable since the region_code is
        # consistent with the user's intent. Mid-word matches are still
        # blocked by the leading lookbehind ("이강남씨" → no match).
    )

    # Phrases that look transactional ("주문") but are actually view-only inquiries
    # (order history, coupon, video review). Detected here so goal_type stays None
    # for these turns — the LLM domain classifier handles them via a single tool
    # call without needing the model→size→qty→shop checklist that goal_type
    # assignment would otherwise enforce.
    # `(?!\s*해|\s*하)` excludes "내 주문해줘" / "내 주문하고 싶어" which are real
    # purchase intents that share the "내 주문" prefix with order-history phrasing.
    _GOAL_VIEW_ONLY_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"주문\s*내역|주문\s*조회|내가\s*주문|내\s*주문(?!\s*해|\s*하)"),
    ]

    # Brand / model keyword patterns. Used by the Coordinator's auto-chain gate to
    # distinguish "벤투스 S2 얼마?" (product-specific transactional query, should
    # chain Discovery→Transaction) from "가격 얼마에요?" (no product, should stay
    # Discovery-only so Discovery can ask which model).
    # Mirrors Discovery Flow B's translation dictionary (Ventus/Kinergy/Optimo/
    # Dynapro/Laufenn) plus carried brands (Michelin/Pirelli/Bridgestone/Continental/
    # Goodyear). Add new brands/models here if Discovery's brand_cd table grows.
    # Includes Korean brand names (미쉐린/피렐리/...) which dominate user input,
    # and select bare model codes for "model-only + size" turns like "HPX
    # 235/55R19 재고확인" — \b word boundaries prevent false positives on
    # common substrings.
    # Goal label map — Korean strings injected into the prompt's `[목표: ...]`
    # block so agents see a human-readable destination rather than the raw enum.
    GOAL_LABELS: ClassVar[dict[str, str]] = {
        "product_recommend": "타이어 추천",
        "product_search": "상품 검색",
        "store_with_stock": "재고 있는 매장 찾기",
        "store_finder": "매장 찾기",
        "price_inquiry": "가격 조회",
        "place_order": "주문 진행",
    }

    # Per-goal step checklist. Each step = (step_id, korean_label, slot_field_set).
    # A step is "done" when ANY slot in the set is non-None (frozenset to mark
    # equivalence — e.g., either tire_model or goods_no satisfies the model step).
    # `product_recommend` has an empty plan: Discovery is tool-driven there, no
    # deterministic checklist to gate progress on.
    GOAL_PLANS: ClassVar[dict[str, list[tuple[str, str, frozenset[str]]]]] = {
        "product_recommend": [],
        # product_search: single-step plan that completes when goods_no resolves.
        # Until then, route to Discovery so search_product_tool runs immediately
        # on bare product-keyword turns ("벤투스 S2", "다이나프로 HPX 어때?",
        # "dynapro HPX, dynapro HP3 중에 최신상품이 뭐야?"). After goods_no is
        # set, no completion-domain is registered → falls through to LLM
        # classifier so the user's next intent (price / stock / order / etc.)
        # determines the chain.
        "product_search": [
            ("search", "상품 검색", frozenset({"goods_no"})),
        ],
        "store_with_stock": [
            ("model", "타이어 모델", frozenset({"tire_model", "goods_no"})),
            ("size", "타이어 사이즈", frozenset({"tire_size"})),
            ("qty", "수량", frozenset({"ord_qty"})),
            ("shop", "매장 선택", frozenset({"shop_id"})),
        ],
        # store_finder: pure store search (no stock/price/order intent).
        # Single-step plan that completes once region resolves. The agent
        # filters/ranks the resulting store list against `user_preferences_text`
        # if present (free-form criteria like "친절한 직원", "워셔액 무료").
        # `shop_id` is intentionally NOT a goal step here — picking a specific
        # store is the user's job after the agent presents the matched list.
        "store_finder": [
            ("region", "지역", frozenset({"region"})),
        ],
        "price_inquiry": [
            ("model", "타이어 모델", frozenset({"tire_model", "goods_no"})),
            ("size", "타이어 사이즈", frozenset({"tire_size"})),
            ("qty", "수량", frozenset({"ord_qty"})),
        ],
        "place_order": [
            ("model", "타이어 모델", frozenset({"tire_model", "goods_no"})),
            ("size", "타이어 사이즈", frozenset({"tire_size"})),
            ("qty", "수량", frozenset({"ord_qty"})),
            ("shop", "매장 선택", frozenset({"shop_id"})),
        ],
    }

    _PRODUCT_KEYWORD_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(
            # Korean brands (primary user input)
            r"벤투스|키네르기|키너지|옵티모|다이나프로|아이온|라우펜|"
            r"마일리지\s*(?:플러스\s*)?[23]\b|마일리지\s*플러스|마일리지\s*타이어|"
            r"미쉐린|피렐리|브리지스톤|콘티넨탈|굿이어|한국타이어|"
            # English brands
            r"Ventus|Kinergy|Optimo|Dynapro|iON|Laufenn|"
            r"Mileage\s*(?:Plus\s*)?[23]\b|Mileage\s*Plus|Mileage\s*Tire|"
            r"Michelin|Pirelli|Bridgestone|Continental|Goodyear|Hankook|"
            # Bare model names (brand omitted by user)
            r"CrossClimate|크로스클라이밋|크로스클라이메이트|"
            r"\bS001\b|\bS007\b|\bER33\b|\bHPX\b|\bHP3\b|"
            r"S\s*FIT|G\s*FIT|에스핏|지핏|i\*?cept|icept|아이셉트|"
            r"\b4S2\b|\bDWS06\b|\bCC7\b|\bPS4S\b|\bPS\s*AS\s*4\b|\bPSAS4\b|\bCUP\s*2\b|\bCUP2\b|\bP7\b|"
            r"P\s?Zero|e\.?Primacy|Hyperion|S\.fit",
            re.IGNORECASE,
        ),
    ]
    _MILEAGE_PRODUCT_LIKE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"마일리지\s*(?:플러스\s*)?[23]\b|마일리지\s*플러스|마일리지\s*타이어|"
        r"Mileage\s*(?:Plus\s*)?[23]\b|Mileage\s*Plus|Mileage\s*Tire",
        re.IGNORECASE,
    )
    _MILEAGE_ATTRIBUTE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"마일리지\s*(?:좋|높|긴|길|성능|중심|우수|뛰어난)|"
        r"오래\s*타|수명|마모|내구|장거리|주행거리",
        re.IGNORECASE,
    )

    @staticmethod
    def _kst_today() -> datetime.date:
        return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()

    @classmethod
    def _extract_requested_cal_day(cls, user_text: str, *, today: datetime.date | None = None) -> str | None:
        base = today or cls._kst_today()
        text = user_text or ""
        if cls._TODAY_DATE_PATTERN.search(text):
            return base.strftime("%Y%m%d")
        relative = cls._RELATIVE_DATE_PATTERN.search(text)
        if relative:
            offset = 1 if relative.group(0) == "내일" else 2
            return (base + datetime.timedelta(days=offset)).strftime("%Y%m%d")
        explicit = cls._EXPLICIT_MD_DATE_PATTERN.search(text)
        if explicit:
            year = int(explicit.group(1) or base.year)
            month = int(explicit.group(2))
            day = int(explicit.group(3))
            try:
                requested = datetime.date(year, month, day)
            except ValueError:
                return None
            if explicit.group(1) is None and requested < base:
                requested = datetime.date(year + 1, month, day)
            return requested.strftime("%Y%m%d")
        return None

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

            # Value changed -> reset dependent slots. Product identity fields
            # invalidate goods_no even on None -> value because goods_no belongs
            # to a concrete product+size combination.
            should_reset_dependents = old_val is not None and old_val != new_val
            if not should_reset_dependents and field in self.PRODUCT_IDENTITY_FIELDS and old_val != new_val:
                should_reset_dependents = any(getattr(merged, dep, None) is not None for dep in self.DEPENDENT_RESETS.get(field, []))
            if should_reset_dependents:
                for dep in self.DEPENDENT_RESETS.get(field, []):
                    logger.info(f"[SLOTS] {field} changed ({old_val} -> {new_val}), resetting {dep}")
                    setattr(merged, dep, None)
                    reset_fields.add(dep)

            setattr(merged, field, new_val)

        # Store reset fields for merge_fill_only to reference
        object.__setattr__(merged, "_reset_fields", reset_fields)
        return merged

    def apply_runtime_values(
        self,
        values: Mapping[str, Any],
        *,
        source: str = "runtime",
        fill_only: bool = False,
    ) -> "ConversationSlots":
        """Apply non-None runtime slot values with source-safe dependency resets.

        This is for slots recovered from tools/templates/history after routing
        has started. It intentionally differs from `merge()`: a newly resolved
        goods_no should not erase the active tire_size unless the incoming
        payload says so, because product switches often reuse size/qty/region.
        """
        del source  # reserved for trace/debug-specific policies if needed
        incoming = {field: value for field, value in dict(values).items() if value is not None}
        updated = self.model_copy()

        for field, new_val in incoming.items():
            if not hasattr(updated, field):
                continue
            old_val = getattr(updated, field)
            if fill_only and old_val is not None:
                continue
            should_reset_dependents = old_val is not None and old_val != new_val
            if not should_reset_dependents and field in self.PRODUCT_IDENTITY_FIELDS and old_val != new_val:
                should_reset_dependents = any(
                    getattr(updated, dep, None) is not None
                    for dep in self.RUNTIME_DEPENDENT_RESETS.get(field, [])
                    if dep not in incoming
                )
            if should_reset_dependents:
                for dep in self.RUNTIME_DEPENDENT_RESETS.get(field, []):
                    if dep in incoming:
                        continue
                    logger.info(
                        "[SLOTS] runtime %s changed (%r -> %r), resetting %s",
                        field,
                        old_val,
                        new_val,
                        dep,
                    )
                    setattr(updated, dep, None)
            setattr(updated, field, new_val)

        return updated

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

        shop_name_match = cls._SHOP_NAME_PATTERN.search(user_text)
        if shop_name_match:
            slots.shop_name = shop_name_match.group(1)

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

        requested_cal_day = cls._extract_requested_cal_day(user_text)
        text_stripped = user_text.strip()
        if cls._TODAY_INSTALL_PATTERN.search(user_text):
            slots.availability_intent = "today_install"
            slots.requested_cal_day = requested_cal_day or cls._kst_today().strftime("%Y%m%d")
        elif requested_cal_day and (
            slots.pending_intent in {"stock", "order", "reservation"}
            or cls.has_store_finder_intent(user_text)
            or len(text_stripped) <= 12
        ):
            slots.requested_cal_day = requested_cal_day

        # Goal type — derived from the same signals as pending_intent plus an
        # explicit recommend check. Recommend takes priority so a fresh
        # "추천해줘" turn flips a stale transactional goal back to discovery.
        # Goal is left None when no signal is present so merge() preserves the
        # previously detected goal across silent turns ("4개", region names).
        # View-only inquiries (order history, coupon, etc.) leave goal_type
        # untouched so the LLM domain classifier handles them — checklist-based
        # fast-path routing would otherwise mis-route them to a product flow.
        is_view_only = any(p.search(user_text) for p in cls._GOAL_VIEW_ONLY_PATTERNS)
        if is_view_only:
            pass
        elif cls.has_mileage_product_search_intent(user_text):
            # "마일리지" is both a product-name token (마일리지 플러스 2/3)
            # and a recommendation attribute. Product-like forms should be
            # searched first; attribute forms such as "마일리지 좋은 타이어" keep
            # the normal recommendation path below.
            slots.goal_type = "product_search"
        elif cls.has_recommend_intent(user_text):
            slots.goal_type = "product_recommend"
        elif slots.pending_intent == "stock":
            slots.goal_type = "store_with_stock"
        elif slots.pending_intent == "price":
            slots.goal_type = "price_inquiry"
        elif slots.pending_intent == "order":
            slots.goal_type = "place_order"
        elif slots.pending_intent == "reservation":
            # 서비스 방문 예약 — region 슬롯 채우기가 1차 미션이므로 store_finder
            # 체크리스트 재사용. 매장 선택 후 일정 잡기(datepick)는 prompt 측에서
            # chain 처리. 별도 reservation goal_type 신설은 follow-up 과제.
            slots.goal_type = "store_finder"
        elif cls.has_store_finder_intent(user_text):
            # Pure store search: no stock/price/order intent, but the user is
            # explicitly asking for a store. Routes through goal-router so the
            # follow-up region answer reuses the originating turn's context
            # (preferences) instead of running a generic store list.
            slots.goal_type = "store_finder"
        elif qty_match is not None and cls.has_product_keyword(user_text):
            # Product keyword + explicit quantity in the SAME turn (e.g.
            # "벤투스 S2 AS 245/45R18 4개") — no 가격/주문 verb, but quantity
            # signals the user is past pure browsing. Escalate to
            # price_inquiry so the goal-router (chat.py `_GOAL_COMPLETE_DOMAIN`)
            # routes to Transaction and `get_final_price_tool` runs
            # deterministically, instead of leaving the LLM to non-
            # deterministically choose between product card and price matrix.
            slots.goal_type = "price_inquiry"
        elif cls.has_product_keyword(user_text):
            # Bare product-keyword turn — no transactional intent, no recommend
            # verb, but a known brand/model is mentioned. Drive Discovery to
            # search the product immediately instead of letting the LLM emit a
            # "검색해 드릴까요?" confirmation quickReply.
            slots.goal_type = "product_search"

        # Region extraction — gated to avoid false positives on common-noun
        # tokens that overlap with Seoul-gu names ("동작 안 해", "중구", "북구"...).
        # Short bare-word turns are treated as slot fills and always tried;
        # longer turns require explicit store-finding context (a store keyword
        # or an active stock intent). For longer turns where context is
        # missing, we skip extraction even if the regex would match — stale
        # region slots persisting from non-store turns are noisier than the
        # occasional missed match.
        should_extract_region = (
            slots.shop_name is None
            and (
                len(text_stripped) <= 8
                or cls.has_store_finder_intent(user_text)
                or slots.pending_intent == "stock"
                or slots.pending_intent == "reservation"
            )
        )
        if should_extract_region:
            region_match = cls._REGION_PATTERN.search(user_text)
            if region_match:
                slots.region = region_match.group("region")

        # Free-form preference capture — only when the turn IS store-related
        # AND carries criteria hints. Skips bland turns like "근처 매장 알려줘"
        # so an empty preference block doesn't get persisted, and skips
        # non-store turns ("강남 가는 길") so unrelated text doesn't leak in.
        is_store_related = (
            cls.has_store_finder_intent(user_text)
            or slots.pending_intent == "stock"
            or slots.pending_intent == "reservation"
        )
        if is_store_related and cls._has_preference_hints(user_text):
            slots.user_preferences_text = user_text.strip()

        return slots

    @classmethod
    def has_store_finder_intent(cls, user_text: str) -> bool:
        """Return True when the user turn explicitly asks for a store/shop.

        Excludes turns that already carry a transactional intent (stock/price/
        order) — those are handled by their respective goal types. The caller
        (`extract_from_user_text`) enforces the priority via the elif chain.
        """
        return any(pattern.search(user_text) for pattern in cls._STORE_FINDER_PATTERNS)

    @classmethod
    def _has_preference_hints(cls, user_text: str) -> bool:
        """Return True when the turn carries soft store-selection criteria
        (친절/얼라인먼트/워셔액/...). Used to gate `user_preferences_text` capture
        so generic store-finder turns don't persist a meaningless preference
        block."""
        return any(pattern.search(user_text) for pattern in cls._PREFERENCE_HINT_PATTERNS)

    @classmethod
    def has_recommend_intent(cls, user_text: str) -> bool:
        """Return True when the user turn explicitly asks for a product recommendation.

        "Recommend" here is **product-recommend** intent (Discovery). When the
        same turn also signals a store-finder context ("분당 매장 추천해줘",
        "근처 지점 추천", "친절한 샵 추천해줘"), the turn is treated as
        store-finder, not product-recommend — return False so the elif chain in
        `extract_from_user_text` falls through to `has_store_finder_intent` and
        the location card is rendered with the store list.

        Used by Coordinator to clear any stale transactional `pending_intent`
        when the user is clearly switching back to discovery.
        """
        if not any(pattern.search(user_text) for pattern in cls._RECOMMEND_PATTERNS):
            return False
        # "매장/지점/샵 추천해줘" → store-finder owns the turn.
        if cls.has_store_finder_intent(user_text):
            return False
        return True

    def evaluate_goal_progress(self) -> tuple[list[str], Optional[str]]:
        """Return (done_step_labels, next_step_label) for the current goal.

        Pure function — reads only this slot instance, no I/O, no LLM. Cost is
        O(plan_steps) ≲ 5 dict/getattr lookups per call.

        Returns:
            ([], None)             when goal_type is unset or has empty plan
            (done, next_step)      when at least one step is unmet
            (all_labels, None)     when every step is done (caller routes to
                                   the goal-completion domain)
        """
        plan = self.GOAL_PLANS.get(self.goal_type or "", [])
        done: list[str] = []
        next_step: Optional[str] = None
        for _step_id, label, required in plan:
            if any(getattr(self, field, None) is not None for field in required):
                done.append(label)
            elif next_step is None:
                next_step = label
        return done, next_step

    def next_goal_step_id(self) -> Optional[str]:
        """Return the first unmet step_id for the current goal, or None.

        Used by the coordinator's goal-based fast-path classifier to map
        next_step → owning domain without paying the LLM-classifier cost.
        """
        plan = self.GOAL_PLANS.get(self.goal_type or "", [])
        for step_id, _label, required in plan:
            if not any(getattr(self, field, None) is not None for field in required):
                return step_id
        return None

    @classmethod
    def has_product_keyword(cls, user_text: str) -> bool:
        """Return True when the user turn contains a known tire brand/model keyword.

        Used by Coordinator's auto-chain gate to avoid firing on no-product
        questions like '가격 얼마에요?' (where Discovery should ask which model
        instead of auto-chaining to Transaction).
        """
        return any(pattern.search(user_text) for pattern in cls._PRODUCT_KEYWORD_PATTERNS)

    @classmethod
    def has_mileage_product_search_intent(cls, user_text: str) -> bool:
        """Return True for product-like Mileage queries, not mileage attributes."""
        if not cls._MILEAGE_PRODUCT_LIKE_PATTERN.search(user_text):
            return False
        return not cls._MILEAGE_ATTRIBUTE_PATTERN.search(user_text)

    def to_prompt_context(self, include_pending_intent: bool = True) -> str:
        """Format slots as a system prompt context string for agent injection.

        Emits up to two blocks:
        - [확인된 고객 정보] — confirmed ENTITY slots only (tire_size, goods_no, etc.).
          Carries the "do not re-ask; use tools for missing fields" instruction.
        - [사용자의 진행 중인 요청] — pending_intent, emitted as an independent hint.
          Does NOT carry the "do not re-ask" instruction, because intent alone is not
          confirmed entity data and an agent may still need to clarify product/store.

        Args:
            include_pending_intent: When True (default), the
                [사용자의 진행 중인 요청] block is emitted. When False, that block
                is suppressed — used for agents that must route purely from prior
                conversation context (Discovery / Support / Leading); only the
                Transaction agent acts directly on the intent slot.

        Returns empty string when no slot is set.
        """
        entity_label_map = {
            "tire_size": "타이어 사이즈",
            "tire_size_front": "전륜 타이어 사이즈",
            "tire_size_rear": "후륜 타이어 사이즈",
            "tire_model": "타이어 모델",
            "goods_no": "상품번호",
            "ord_qty": "수량",
            "shop_id": "매장코드",
            "shop_name": "매장명",
            "car_model": "차량 모델",
            "car_no": "차량번호",
            "car_lnc_cd": "차량코드",
            "mbr_car_reg_seq": "차량등록시퀀스",
            "region": "지역",
            "availability_intent": "장착 가능 조건",
            "requested_cal_day": "요청 장착일",
            "rsv_hour": "요청 예약시간",
            "payment_amount": "결제금액",
        }

        # Map pending_intent enum value → Korean label displayed in the prompt.
        intent_label_map = {
            "price": "가격 조회",
            "stock": "재고 확인",
            "order": "주문 진행",
            "reservation": "방문 예약",
        }

        entity_lines = []
        for field, label in entity_label_map.items():
            val = getattr(self, field)
            if val is None:
                continue
            if field == "payment_amount":
                # 천단위 콤마 + 원 단위 명시 — LLM 이 그대로 인용하기 좋은 형식.
                # 할부 계산 등에서 이 값을 임의로 변형하지 않도록 "이미 산출된 총액" 임을 분명히.
                entity_lines.append(f"- {label}: {val:,}원 (이미 산출된 총 결제금액 — 단가×수량 재계산 금지)")
            else:
                entity_lines.append(f"- {label}: {val}")
        if (
            self.tire_size
            and self.tire_size_front
            and self.tire_size_rear
            and self.tire_size_front != self.tire_size_rear
            and self.tire_size in {self.tire_size_front, self.tire_size_rear}
        ):
            entity_lines.append("- 수량 제한: 전/후륜 규격 상이 차량은 현재 선택한 규격 기준 최대 2개")

        blocks: list[str] = []

        # Goal block — emitted FIRST so the agent reads "destination" before
        # "current facts". One compact line keeps the token cost minimal
        # (~30-80 chars) while still surfacing done/next progress so the agent
        # can drive the user toward the next missing step instead of rehashing
        # the whole flow. Always emitted regardless of include_pending_intent
        # because goal awareness is useful for every agent (Discovery,
        # Transaction, Support, Leading).
        if self.goal_type:
            goal_label = self.GOAL_LABELS.get(self.goal_type, self.goal_type)
            done, next_step = self.evaluate_goal_progress()
            parts = [f"목표: {goal_label}"]
            if done:
                parts.append(f"완료: {' · '.join(done)}")
            if next_step:
                parts.append(f"다음: {next_step}")
            blocks.append("[" + " | ".join(parts) + "]")

        if entity_lines:
            blocks.append(
                "\n".join([
                    "[확인된 고객 정보 - 이 정보는 다시 묻지 마세요]",
                    *entity_lines,
                    "[위 정보가 없는 항목은 tool을 호출하여 확인하세요. 유저에게 묻지 마세요.]",
                ])
            )

        # Free-form store-selection preferences captured on the originating
        # turn. Persists across the region clarification so the agent can
        # filter/rank store search results against the user's actual criteria
        # (친절한 직원, 얼라인먼트, 워셔액 무료 etc.) once region resolves.
        # Confirmable items in BE data → use them to filter/order; non-data
        # items (분위기/직원 친절도) → mention and offer to confirm via the
        # store directly rather than fabricating an answer.
        if self.user_preferences_text:
            blocks.append(
                "[사용자의 매장 선호 조건]\n"
                f"{self.user_preferences_text}\n"
                "→ 매장 결과 제시 시 위 조건을 반드시 참고하여 추천하거나, "
                "매칭 여부를 응답에 명시하세요. BE 데이터로 확인 가능한 항목은 "
                "결과 필터링/순위에 반영하고, 확인이 어려운 항목은 "
                "'매장 직원에게 문의 가능합니다' 식으로 안내하세요. "
                "이 조건들을 무시하고 일반 매장 리스트만 반환하지 마세요."
            )

        if include_pending_intent and self.pending_intent is not None:
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


class CanonicalSlotState(BaseModel):
    """Normalized slot view used by policy/reset code without changing the external slot API."""

    common: dict[str, Any] = {}
    product: dict[str, Any] = {}
    store: dict[str, Any] = {}
    price: dict[str, Any] = {}
    contexts: dict[str, Any] = {}

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = (
        "tire_size",
        "tire_size_front",
        "tire_size_rear",
        "vehicle_type",
        "car_lnc_cd",
        "car_no",
        "car_model",
        "ord_qty",
        "region",
    )
    PRODUCT_FIELDS: ClassVar[tuple[str, ...]] = (
        "goods_no",
        "tire_model",
        "pending_product_name",
    )
    STORE_FIELDS: ClassVar[tuple[str, ...]] = (
        "shop_id",
        "shop_name",
        "requested_cal_day",
        "rsv_hour",
    )
    PRICE_FIELDS: ClassVar[tuple[str, ...]] = (
        "payment_amount",
        "price_facts",
        "coupon_facts",
    )
    CONTEXT_FIELDS: ClassVar[tuple[str, ...]] = (
        "recommendation_context",
        "comparison_context",
        "availability_context",
        "order_context",
        "quantity_comparison_context",
    )

    @classmethod
    def from_slots(cls, slots: ConversationSlots) -> "CanonicalSlotState":
        def _value(value: Any) -> Any:
            if isinstance(value, RecommendationContext):
                return value.to_policy_dict()
            if isinstance(value, ComparisonContext):
                return value.to_policy_dict()
            if isinstance(value, BaseModel):
                return value.model_dump(exclude_none=True)
            return value

        def _group(fields: tuple[str, ...]) -> dict[str, Any]:
            return {
                field: _value(getattr(slots, field))
                for field in fields
                if getattr(slots, field, None) is not None
            }

        return cls(
            common=_group(cls.COMMON_FIELDS),
            product=_group(cls.PRODUCT_FIELDS),
            store=_group(cls.STORE_FIELDS),
            price=_group(cls.PRICE_FIELDS),
            contexts=_group(cls.CONTEXT_FIELDS),
        )

    @classmethod
    def reset_for_new_recommendation(
        cls,
        slots: ConversationSlots,
        *,
        recommendation_context: Mapping[str, Any] | None = None,
        current_tire_size: str | None = None,
        current_product_name: str | None = None,
    ) -> dict[str, Any]:
        """Reset flow-specific state for a new recommendation while preserving common fitment slots."""

        cleared: dict[str, Any] = {}
        if current_tire_size:
            slots.tire_size = current_tire_size
        if recommendation_context:
            slots.recommendation_context = RecommendationContext.from_mapping(recommendation_context)

        product_reset_fields = (
            "goods_no",
            "payment_amount",
            "price_facts",
            "coupon_facts",
            "order_context",
            "pending_product_name",
            "pending_quantity_options",
            "pending_required_slot",
        )
        for field in product_reset_fields:
            if getattr(slots, field, None) is not None:
                cleared[field] = getattr(slots, field)
                setattr(slots, field, None)

        if not current_product_name and slots.tire_model is not None:
            cleared["tire_model"] = slots.tire_model
            slots.tire_model = None

        return cleared
