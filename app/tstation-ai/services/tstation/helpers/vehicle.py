from __future__ import annotations

import logging
import re
from typing import Any

from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.ui_action_policy import normalize_vehicle_type_from_car_type

logger = logging.getLogger(__name__)

# "Non-self car" negation: user explicitly excludes their registered/saved cars
# and asks about a different vehicle model. When this fires, any stale
# tire_size / goods_no / car_model carried over from a prior turn refers to the
# WRONG vehicle and must be cleared before the slot context is injected into
# the agent prompt — otherwise the LLM reuses the stale size and ignores the
# car model the user just named (see CAR MODEL DISPLAY rule in
# b_discovery_agent/agent.py).
#
# Covers:
#   "내차말고", "내차말구", "내차말로", "내 차 말고", "내차 말고", "내차아닌", "내 차 아닌",
#   "내차아니라", "내 차가 아닌", "내차빼고", "내 차 빼고",
#   "저장차 아닌", "저장차말고", "등록차 아닌", "등록차말고",
#   "보유차 아닌", "보유한 차 말고",
#   "다른 차종", "다른 차"
_NON_SELF_CAR_RE = re.compile(
    r"(내\s*차|저장\s*차|등록\s*차|보유\s*차|보유한\s*차|내가\s*가진\s*차)"
    r"\s*(말고|말구|말로|아닌|아니라|아니고|빼고|이외|제외)"
    r"|다른\s*차(?:종)?",
    re.IGNORECASE,
)

_VEHICLE_PLATE_RE = re.compile(r"\d{2,3}\s*[가-힣]\s*\d{4}")
_VEHICLE_BOUND_REQUEST_RE = re.compile(
    r"내\s*차|내차|내\s*차량|내차량|차량번호|차\s*번호|"
    r"내\s*[0-9a-zA-Z가-힣]+|"
    r"\d{2,3}\s*[가-힣]\s*\d{4}",
    re.IGNORECASE,
)
_VEHICLE_LIST_REQUEST_RE = re.compile(
    r"내\s*차\s*목록|내차\s*목록|내차목록|내\s*차량|내차량|보유\s*차량|보유차량|"
    r"보유차량\s*확인|내\s*등록차|등록차량|등록차|내\s*차\s*보여|내차\s*보여|내차보여|"
    r"내\s*차\s*(?:사이즈|규격|로\s*다시)|내차\s*(?:사이즈|규격|로\s*다시)",
    re.IGNORECASE,
)
_VEHICLE_RECOMMENDATION_TEXT_RE = re.compile(
    r"추천|맞는\s*타이어|타이어\s*보여|타이어\s*찾|타이어\s*알려|"
    r"장착\s*가능|호환|끼워",
    re.IGNORECASE,
)
_VEHICLE_OWNER_TEXT_RE = re.compile(
    r"(?:(?P<car_no>\d{2,3}\s?[가-힣]\s?\d{4})\s+(?P<owner_nm>[가-힣]{2,4})"
    r"|(?P<owner_nm_prefix>[가-힣]{2,4})\s+(?P<car_no_suffix>\d{2,3}\s?[가-힣]\s?\d{4}))"
)
_OWNER_NAME_ONLY_RE = re.compile(r"^\s*[가-힣]{2,4}\s*$")
_VEHICLE_MATCH_STOPWORDS = {
    "내",
    "내차",
    "차",
    "차량",
    "차량번호",
    "번호",
    "알지",
    "맞는",
    "타이어",
    "추천",
    "보여줘",
    "보여",
    "찾아줘",
    "알려줘",
    "엔진오일",
    "교체",
    "언제",
    "정비",
    "일정",
    "시기",
    "이건데",
    "있던데",
    "뭐",
    "뭘",
    "뭘로",
    "그럼",
    "이거",
    "같은데",
    "같은",
    "사이즈",
    "규격",
    "봐야해",
    "봐야",
    "어떻게",
    "어느",
}
_VEHICLE_SIZE_GUIDANCE_TEXT_RE = re.compile(
    r"전\s*/?\s*후륜|전륜|후륜|앞뒤|앞\s*뒤|"
    r"어느\s*사이즈|뭘로\s*.*사이즈|"
    r"규격이\s*다르|사이즈가\s*다르",
    re.IGNORECASE,
)
_VEHICLE_INFO_TEXT_RE = re.compile(
    r"규격|사이즈|인치|편평비|단면폭|하중지수|속도등급|전륜|후륜|앞뒤|"
    r"어떻게\s*봐|뭘로\s*봐|어느\s*걸\s*봐|무슨\s*규격|몇\s*인치",
    re.IGNORECASE,
)
_OWNED_VEHICLE_SELECTION_CTA_RE = re.compile(
    r"^\s*(보유\s*차량\s*중\s*선택|내\s*차량\s*보기|내\s*차\s*보기|내\s*차(?:량)?로\s*찾기|"
    r"차량\s*(?:정보로\s*)?찾기|차량\s*선택해서\s*찾기)\s*$",
    re.IGNORECASE,
)
_VEHICLE_TYPE_COMPATIBILITY_TEXT_RE = re.compile(
    r"(?=.*(?:suv|SUV|에스유브이))(?=.*(?:승용|세단|일반\s*타이어))"
    r"(?=.*(?:끼워|써도|사용|장착|맞|호환|가능|돼|되))",
    re.IGNORECASE,
)


def _normalize_vehicle_match_text(value: object) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "")).lower()


def _strip_vehicle_particle(token: str) -> str:
    stripped = token
    for suffix in ("으로", "에서", "하고", "이랑", "처럼", "이라", "이고", "인데", "으로요"):
        if len(stripped) > len(suffix) + 1 and stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            break
    for suffix in ("은", "는", "이", "가", "을", "를", "에", "도", "와", "과", "로", "요"):
        if len(stripped) > len(suffix) + 1 and stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            break
    return stripped


def _vehicle_match_tokens(user_text: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.findall(r"[0-9a-zA-Z가-힣]+", user_text or ""):
        token = _strip_vehicle_particle(_normalize_vehicle_match_text(raw))
        if len(token) < 2 or token in _VEHICLE_MATCH_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _vehicle_candidate_tokens(car: dict[str, Any], meta: dict[str, Any]) -> set[str]:
    source_values = [
        car.get("licensePlate"),
        car.get("info"),
        car.get("description"),
        meta.get("carNo"),
        meta.get("carLncCd"),
        meta.get("carMaker"),
        meta.get("carModelDet"),
        meta.get("carName"),
        meta.get("carTrim"),
        meta.get("carEngine"),
    ]
    tokens: set[str] = set()
    for value in source_values:
        for raw in re.findall(r"[0-9a-zA-Z가-힣]+", str(value or "")):
            token = _normalize_vehicle_match_text(raw)
            if len(token) >= 2:
                tokens.add(token)
    return tokens


def _vehicle_owner_lookup_prompt_event(plate: str, owner_provided: bool) -> dict:
    if owner_provided:
        assistant_response = (
            f"입력하신 **{plate}** 차량 정보를 확인하지 못했어요.\n"
            "차량번호와 소유주명을 다시 확인해 주세요."
        )
        quick_replies = [
            {"label": "차번+이름 다시 입력", "domain": "DISCOVERY"},
            {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            {"label": "내 차량 보기", "domain": "DISCOVERY"},
        ]
    else:
        assistant_response = (
            f"**{plate}** 은(는) 등록된 차량 목록에 없어요.\n"
            "해당 차량으로 찾으시려면 **차량번호 + 소유주명**을 입력해 주세요. "
            "예: 12가3456 홍길동"
        )
        quick_replies = [
            {"label": "차번+이름으로 검색", "domain": "DISCOVERY"},
            {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            {"label": "내 차량 보기", "domain": "DISCOVERY"},
        ]
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": quick_replies,
            "predictedDomains": ["DISCOVERY"],
        },
    }


def _non_self_vehicle_plate_owner_lookup_plate(user_text: str | None) -> str | None:
    """Return the plate for "not my car + plate only" owner-lookup requests."""
    text = user_text or ""
    non_self_match = _NON_SELF_CAR_RE.search(text)
    if not non_self_match:
        return None
    remainder = _NON_SELF_CAR_RE.sub(" ", text, count=1).strip()
    if _normalize_vehicle_owner_lookup_text(remainder):
        return None
    plate_match = _VEHICLE_PLATE_RE.search(text)
    if not plate_match:
        return None
    return re.sub(r"[^0-9가-힣]", "", plate_match.group(0))


def _normalize_vehicle_owner_lookup_text(user_text: str | None) -> str | None:
    """Normalize owner/plate lookup input to the tool-friendly "car_no owner_nm" order."""
    text = (user_text or "").strip()
    if not text:
        return None
    if _NON_SELF_CAR_RE.search(text):
        text = _NON_SELF_CAR_RE.sub(" ", text, count=1).strip()
    match = _VEHICLE_OWNER_TEXT_RE.fullmatch(text)
    if not match:
        return None
    car_no = match.group("car_no") or match.group("car_no_suffix")
    owner_nm = match.group("owner_nm") or match.group("owner_nm_prefix")
    if not car_no or not owner_nm:
        return None
    normalized_car_no = re.sub(r"[^0-9가-힣]", "", car_no)
    return f"{normalized_car_no} {owner_nm}"


def _non_self_vehicle_plate_owner_lookup_prompt_event(user_text: str | None) -> dict | None:
    plate = _non_self_vehicle_plate_owner_lookup_plate(user_text)
    if not plate:
        return None
    assistant_response = (
        f"**{plate}** 차량으로 확인하려면 **차량번호 + 소유주명**이 필요해요.\n"
        "소유주명만 이어서 입력해 주셔도 차량 조회로 연결할게요. "
        f"예: {plate} 홍길동"
    )
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_non_self_vehicle_owner_lookup_prompt",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": [
                {"label": "차번+이름으로 검색", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "내 차량 보기", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
    }


def _coerce_unmatched_vehicle_listcar_to_owner_prompt(event: dict, user_text: str | None) -> dict | None:
    if event.get("template") != "listCar":
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None
    plate_match = _VEHICLE_PLATE_RE.search(user_text or "")
    if not plate_match:
        return None
    requested_plate = re.sub(r"[^0-9가-힣]", "", plate_match.group(0))
    metadata = event_data.get("metadata")
    if not isinstance(metadata, list):
        return None
    returned_plates = {
        re.sub(r"[^0-9가-힣]", "", str(meta.get("carNo") or ""))
        for meta in metadata
        if isinstance(meta, dict)
    }
    if requested_plate and requested_plate not in returned_plates:
        return _vehicle_owner_lookup_prompt_event(
            requested_plate,
            owner_provided=bool(_VEHICLE_OWNER_TEXT_RE.search(user_text or "")),
        )
    return None


def _should_reuse_pending_vehicle_lookup_car_no(
    latest_quickreply_tmpl: dict | None,
    user_text: str | None,
    pending_car_no: str | None,
) -> bool:
    if not pending_car_no or not _OWNER_NAME_ONLY_RE.match(user_text or ""):
        return False
    # Primary condition: the immediately previous turn left an unmatched plate
    # waiting for owner-name completion, and the user now provided only a
    # plausible Korean owner name. This is enough to safely reconstruct
    # "car_no + owner_nm" even if template-history persistence races.
    if not isinstance(latest_quickreply_tmpl, dict):
        return True
    template_data = latest_quickreply_tmpl.get("data")
    if not isinstance(template_data, dict):
        return True
    assistant_response = str(template_data.get("assistantResponse") or "")
    quick_replies = template_data.get("quickReplies") or []
    labels = {
        str(chip.get("label") or "").strip()
        for chip in quick_replies
        if isinstance(chip, dict)
    }
    return (
        "차량번호 + 소유주명" in assistant_response
        or "차량번호와 소유주명" in assistant_response
        or "차번+이름으로 검색" in labels
        or "차번+이름 다시 입력" in labels
    )


def _build_vehicle_size_guidance_event(selected_vehicle: dict) -> dict | None:
    selected_car = selected_vehicle.get("car") or {}
    selected_meta = selected_vehicle.get("meta") or {}
    selection_context = selected_vehicle.get("selection_context") or {}
    front_size = normalize_tire_size(
        str(
            selected_meta.get("tireSize")
            or selected_meta.get("tireSizeFr")
            or selected_meta.get("tire_size_fr")
            or selected_meta.get("tire_size")
            or ""
        )
    )
    rear_size = normalize_tire_size(
        str(
            selected_meta.get("tireSizeRe")
            or selected_meta.get("tireSizeRear")
            or selected_meta.get("tire_size_re")
            or ""
        )
    )
    car_no = str(
        selected_meta.get("carNo")
        or selected_meta.get("car_no")
        or selected_car.get("licensePlate")
        or ""
    ).strip()
    if not front_size and not rear_size:
        return None

    car_display_name = str(
        selected_meta.get("carModelDet")
        or selected_meta.get("car_model_det")
        or selected_meta.get("carName")
        or selected_meta.get("carNm")
        or selected_meta.get("car_nm")
        or selected_car.get("info")
        or selected_car.get("description")
        or ""
    ).strip()
    car_maker = str(selected_meta.get("carMaker") or "").strip()
    if car_display_name and car_maker and car_maker not in car_display_name:
        car_display_name = f"{car_maker} {car_display_name}".strip()

    selected_size = ""
    if front_size and rear_size and front_size != rear_size:
        size_text = f"앞 타이어: {front_size}\n뒤 타이어: {rear_size}"
    else:
        selected_size = front_size or rear_size
        size_text = f"해당 차량의 타이어 사이즈는 {selected_size}입니다."

    response_lines = []
    if car_no and car_display_name:
        response_lines.append(f"{car_no} 차량은 {car_display_name}로 확인됐어요.")
    elif car_no:
        response_lines.append(f"{car_no} 차량 정보를 확인했어요.")
    if front_size and rear_size and front_size != rear_size:
        response_lines.append("해당 차량의 타이어 사이즈는")
        response_lines.append(size_text)
    else:
        response_lines.append(size_text)
    response_lines.append("무엇을 도와드릴까요?")
    response = "\n\n".join(
        [response_lines[0], "\n".join(response_lines[1:-1]), response_lines[-1]]
        if len(response_lines) >= 3
        else response_lines
    )

    vehicle_type = str(
        normalize_vehicle_type_from_car_type(
            selected_meta.get("carType") or selected_meta.get("car_type"),
            fallback_text=car_display_name,
        )
        or ""
    ).strip()
    cta_metadata = {
        "car_no": car_no,
        "car_lnc_cd": str(selected_meta.get("carLncCd") or selected_meta.get("car_lnc_cd") or "").strip() or None,
        "tire_size": selected_size or None,
        "tire_size_front": front_size or None,
        "tire_size_rear": rear_size or None,
        "vehicle_type": vehicle_type or None,
    }

    quick_replies = [
        {
            "label": "타이어 추천",
            "domain": "DISCOVERY",
            "cta_action": "recommend_by_selected_vehicle_size",
            "source_intent": str(selection_context.get("source_intent") or "vehicle_tire_size_lookup"),
            "expected_contract_intent": "product_recommendation",
            "metadata": {k: v for k, v in cta_metadata.items() if v not in (None, "")},
        },
        {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
    ]

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_vehicle_tire_size_lookup",
        "data": {
            "assistantResponse": response,
            "quickReplies": quick_replies,
            "predictedDomains": ["DISCOVERY"],
            "metadata": {
                "responseShapeKey": "vehicle_tire_size_lookup",
                "response_shape_key": "vehicle_tire_size_lookup",
                "selectedCarNo": car_no,
                "selected_car_no": car_no,
                "selectedTireSize": selected_size or front_size or rear_size,
                "selected_tire_size": selected_size or front_size or rear_size,
            },
        },
    }


def _build_vehicle_information_event(selected_vehicle: dict, user_text: str) -> dict | None:
    if _VEHICLE_SIZE_GUIDANCE_TEXT_RE.search(user_text or ""):
        return _build_vehicle_size_guidance_event(selected_vehicle)

    if not _VEHICLE_INFO_TEXT_RE.search(user_text or ""):
        return None

    selected_car = selected_vehicle.get("car") or {}
    selected_meta = selected_vehicle.get("meta") or {}
    raw_available_sizes = selected_meta.get("availableSizes") or selected_meta.get("available_sizes") or []
    available_sizes: list[str] = []
    if isinstance(raw_available_sizes, list):
        for raw_size in raw_available_sizes:
            normalized_size = normalize_tire_size(str(raw_size or ""))
            if normalized_size and normalized_size not in available_sizes:
                available_sizes.append(normalized_size)
    front_size = str(selected_meta.get("tireSize") or "").strip()
    rear_size = str(selected_meta.get("tireSizeRe") or "").strip()
    car_info = str(selected_car.get("info") or selected_car.get("description") or "선택하신 차량").strip()
    car_no = str(selected_meta.get("carNo") or selected_car.get("licensePlate") or "").strip()

    if len(available_sizes) >= 2:
        response = (
            f"**{car_info} ({car_no})** 차량으로 확인했어요.\n\n"
            f"확인된 규격이 여러 개예요: {', '.join(f'**{size}**' for size in available_sizes)}\n\n"
            "어떤 규격 기준으로 추천을 이어갈지 선택해 주세요."
        )
        return {
            "type": "data",
            "template": "quickReply",
            "source_domain": "discovery",
            "assistant_response_source": "code_vehicle_multi_size_selection",
            "data": {
                "assistantResponse": response,
                "quickReplies": [{"label": size, "domain": "DISCOVERY"} for size in available_sizes[:8]],
                "predictedDomains": ["DISCOVERY"],
                "metadata": {"availableSizes": available_sizes, "response_shape_key": "vehicle_size_selection"},
            },
        }

    size_line = ""
    if front_size and rear_size and front_size != rear_size:
        size_line = f"전륜 **{front_size}**, 후륜 **{rear_size}**"
    elif front_size or rear_size:
        size_line = f"전/후륜 동일 규격 **{front_size or rear_size}**"

    response = f"**{car_info} ({car_no})** 차량으로 확인했어요."
    if size_line:
        response += f"\n\n현재 확인되는 규격은 {size_line}예요."
    response += "\n\n원하시는 항목을 선택해 주시면 그 기준으로 이어서 도와드릴게요."

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_vehicle_auto_select",
        "data": {
            "assistantResponse": response,
            "quickReplies": [
                {"label": "전/후륜 규격 보기", "domain": "DISCOVERY"},
                {"label": "맞는 타이어 추천", "domain": "DISCOVERY"},
                {"label": "동일 상품 찾기", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
    }


def _coerce_vehicle_type_compatibility_listcar_to_quickreply(event: dict, user_query: str | None) -> dict | None:
    """Answer SUV/passenger-tire compatibility questions instead of showing registered cars."""
    if event.get("template") != "listCar":
        return None
    source_domain = str(event.get("source_domain") or "").lower()
    if source_domain != "discovery":
        return None
    if not _VEHICLE_TYPE_COMPATIBILITY_TEXT_RE.search(user_query or ""):
        return None
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": event.get("source_domain"),
        "assistant_response_source": "code_mapper_vehicle_type_compatibility_guard",
        "data": {
            "assistantResponse": (
                "SUV에는 승용차/세단용 타이어를 임의로 장착하는 건 권장하지 않아요. "
                "같은 사이즈처럼 보여도 하중지수와 설계 기준이 다를 수 있어서, "
                "차량 규격에 맞는 SUV용 또는 SUV 호환 타이어로 확인하는 게 안전합니다."
            ),
            "quickReplies": [
                {"label": "SUV용 추천", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "내 차량으로 확인", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
    }


def _vehicle_type_compatibility_guard_event(user_text: str) -> dict | None:
    """Answer vehicle-category tire compatibility as general guidance before car-list lookup."""
    if not _VEHICLE_TYPE_COMPATIBILITY_TEXT_RE.search(user_text or ""):
        return None
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_vehicle_type_compatibility_guard",
        "data": {
            "assistantResponse": (
                "SUV에는 승용차/세단용 타이어를 임의로 장착하는 건 권장하지 않아요. "
                "같은 사이즈처럼 보여도 하중지수와 설계 기준이 다를 수 있어서, "
                "차량 규격에 맞는 SUV용 또는 SUV 호환 타이어로 확인하는 게 안전합니다."
            ),
            "quickReplies": [
                {"label": "SUV용 추천", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "내 차량으로 확인", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
    }
