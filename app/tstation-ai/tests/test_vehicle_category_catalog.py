import pytest

from services.tstation.policies.vehicle_category_catalog import (
    VehicleModelMatch,
    match_vehicle_model_category,
)


def _category(text: str) -> str | None:
    match = match_vehicle_model_category(text)
    return match.category if match is not None else None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # SUV — Korean alias + spelling variants + Latin alias
        ("팰리세이드 타이어 추천", "suv"),
        ("펠리세이드 추천해줘", "suv"),
        ("palisade tire", "suv"),
        ("싼타페 타이어", "suv"),
        ("산타페 추천", "suv"),
        ("소렌토 타이어 추천", "suv"),
        ("G바겐 타이어 추천해줘", "suv"),
        # Passenger
        ("쏘나타 타이어 추천", "passenger"),
        ("소나타 추천해줘", "passenger"),
        ("E클래스 타이어", "passenger"),
        ("그랜저 추천", "passenger"),
        # truck_van
        ("포터 타이어 추천", "truck_van"),
        ("카니발 추천해줘", "truck_van"),
        # ev — dedicated electric only
        ("모델Y 타이어 추천", "ev"),
        ("아이오닉5 추천", "ev"),
        ("아이오닉 6 타이어", "ev"),
    ],
)
def test_basic_category_matching(text: str, expected: str) -> None:
    assert _category(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Dual-fuel / ICE models must map to body type, never "ev".
        ("코나 추천", "suv"),
        ("니로 타이어 추천", "suv"),
        ("G80 타이어 추천", "passenger"),
        ("GV70 추천해줘", "suv"),
        # Explicitly-EV models still resolve to ev.
        ("모델Y 추천", "ev"),
        ("아이오닉5 추천", "ev"),
    ],
)
def test_ev_only_rule(text: str, expected: str) -> None:
    assert _category(text) == expected


def test_entry_order_specific_name_wins_over_prefix() -> None:
    assert _category("렉스턴 스포츠 타이어 추천") == "truck_van"
    assert _category("렉스턴 타이어 추천") == "suv"


def test_masked_text_blanks_model_scenario_keyword() -> None:
    match = match_vehicle_model_category("렉스턴 스포츠 타이어 추천")
    assert match is not None
    assert "스포츠" not in match.masked_text
    # non-model words survive so scenario extraction still works
    assert "추천" in match.masked_text


def test_masked_text_keeps_real_scenario_keyword() -> None:
    match = match_vehicle_model_category("팰리세이드 조용한 타이어 추천")
    assert match is not None
    assert match.category == "suv"
    assert "조용한" in match.masked_text
    assert "팰리세이드" not in match.masked_text


def test_latin_alias_boundary() -> None:
    # "X5" must not match inside "EX5"
    assert match_vehicle_model_category("EX5 타이어") is None
    # "K5" matches standalone but not inside a longer trim number
    assert _category("K5 타이어 추천") == "passenger"
    assert match_vehicle_model_category("K50 타이어") is None


def test_korean_particle_suffix_still_matches() -> None:
    assert _category("팰리세이드에 맞는 타이어 추천") == "suv"
    assert _category("팰리세이드는 어떤 타이어가 좋아?") == "suv"


def test_porter_not_matched_inside_supporter() -> None:
    assert match_vehicle_model_category("서포터 타이어") is None
    assert _category("포터 타이어 추천") == "truck_van"


def test_no_model_returns_none() -> None:
    assert match_vehicle_model_category("가성비 타이어 추천해줘") is None
    assert match_vehicle_model_category("전기차 타이어 추천") is None
    assert match_vehicle_model_category("") is None


def test_return_type_and_model_name() -> None:
    match = match_vehicle_model_category("팰리세이드 타이어 추천")
    assert isinstance(match, VehicleModelMatch)
    assert match.model == "팰리세이드"
    assert match.category == "suv"
