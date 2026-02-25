import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas import CompatibilityResponse, TireSpec

router = APIRouter(
    prefix="/api/compatibility",
    tags=["Product Compatibility AF - 차량 및 상품 호환 검증"],
)


# --------------------------------------------------------------------------- #
#  SQL 상수                                                                     #
# --------------------------------------------------------------------------- #

# 차량 타이어 사이즈 조회 (PR_CAR_BASE + PR_CAR_ATTR)
CAR_TIRE_SQL = text("""
    SELECT a.TIRE_SIZE_FR, a.TIRE_SIZE_RE
    FROM PR_CAR_BASE b
    JOIN PR_CAR_ATTR a ON b.CAR_NO = a.CAR_NO
    WHERE b.CAR_NO = :car_no
""")

# 상품 타이어 스펙 조회 (PR_GOODS_BASE)
GOODS_SPEC_SQL = text("""
    SELECT TIRE_WIDTH, TIRE_SERIES, INCH
    FROM PR_GOODS_BASE
    WHERE GOODS_NO = :goods_no
""")


# --------------------------------------------------------------------------- #
#  내부 유틸                                                                    #
# --------------------------------------------------------------------------- #

# 타이어 사이즈 파싱: "205/55R16" → (205, 55, 16), 파싱 실패 시 None
_TIRE_RE = re.compile(r"^(\d+)/(\d+)R(\d+)$", re.IGNORECASE)


def _parse_tire_size(size: Optional[str]) -> Optional[tuple[int, int, int]]:
    if not size:
        return None
    m = _TIRE_RE.match(size.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _is_compatible(
    tire_size: Optional[str],
    width: Optional[int],
    series: Optional[int],
    inch: Optional[int],
) -> bool:
    """차량 타이어 사이즈 문자열과 상품 스펙을 비교하여 호환 여부를 반환합니다."""
    parsed = _parse_tire_size(tire_size)
    if parsed is None or width is None or series is None or inch is None:
        return False
    car_width, car_series, car_inch = parsed
    return car_width == width and car_series == series and car_inch == inch


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.get(
    "",
    response_model=CompatibilityResponse,
    summary="차량-상품 타이어 호환 검증",
    description=(
        "차량번호(CAR_NO)로 PR_CAR_BASE + PR_CAR_ATTR에서 전/후륜 타이어 사이즈를 조회하고, "
        "상품번호(GOODS_NO)로 PR_GOODS_BASE에서 타이어 스펙(단면폭/편평비/인치)을 조회하여 "
        "호환 여부를 반환합니다. 카젠 API 연동 전까지 내부 DB 정보를 우선 활용합니다."
    ),
)
async def check_compatibility(
    car_no: str = Query(..., description="차량 번호"),
    goods_no: str = Query(..., description="상품 번호"),
    db: AsyncSession = Depends(get_db),
) -> CompatibilityResponse:

    # ── 1. 차량 타이어 사이즈 조회 ───────────────────────────────────────────
    car_row = (
        await db.execute(CAR_TIRE_SQL, {"car_no": car_no})
    ).mappings().first()

    if car_row is None:
        raise HTTPException(status_code=404, detail=f"차량 정보를 찾을 수 없습니다: {car_no}")

    tire_size_fr = car_row["tire_size_fr"]
    tire_size_re = car_row["tire_size_re"]

    # ── 2. 상품 타이어 스펙 조회 ─────────────────────────────────────────────
    goods_row = (
        await db.execute(GOODS_SPEC_SQL, {"goods_no": goods_no})
    ).mappings().first()

    if goods_row is None:
        raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {goods_no}")

    tire_width = int(goods_row["tire_width"]) if goods_row["tire_width"] is not None else None
    tire_series = int(goods_row["tire_series"]) if goods_row["tire_series"] is not None else None
    inch = int(goods_row["inch"]) if goods_row["inch"] is not None else None

    # ── 3. 호환 여부 판정 ────────────────────────────────────────────────────
    compat_fr = _is_compatible(tire_size_fr, tire_width, tire_series, inch)
    compat_re = _is_compatible(tire_size_re, tire_width, tire_series, inch)

    return CompatibilityResponse(
        car_no=car_no,
        goods_no=goods_no,
        tire_size_fr=tire_size_fr,
        tire_size_re=tire_size_re,
        goods_spec=TireSpec(tire_width=tire_width, tire_series=tire_series, inch=inch),
        is_compatible_fr=compat_fr,
        is_compatible_re=compat_re,
        is_compatible=compat_fr and compat_re,
    )
