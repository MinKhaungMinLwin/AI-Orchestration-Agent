from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas import RecommendationResponse, RcmdGoodsItem

router = APIRouter(
    prefix="/api/recommendations",
    tags=["Product Recommendation AF - 상품 추천"],
)

# 가성비 Good 기준 가격 상한 (원)
_VALUE_PRICE_LIMIT = 200_000


class RcmdType(str, Enum):
    tstation = "tstation"  # 티스테이션 추천
    discount = "discount"  # 최고 할인율
    value = "value"        # 가성비 Good


# --------------------------------------------------------------------------- #
#  SQL 상수                                                                     #
# --------------------------------------------------------------------------- #

# 1. 티스테이션 추천: FST_DISP_YN = 'Y', TOT_SCR * 10 높은 순
TSTATION_SQL = text("""
    SELECT g.GOODS_NO,
           g.GOODS_NM,
           d.EXTRA_FVR_SALE_PRC,
           d.EXTRA_FVR_SALE_PER,
           (r.TOT_SCR * 10) AS RCMD_SCR,
           r.T_COMFORT,
           r.T_SILENCE,
           r.T_LIFE_SPAN,
           r.T_FUEL_EFF_CONVERT
    FROM PR_GOODS_BASE g
    JOIN PR_GOODS_RCMD_SUM r         ON g.GOODS_NO = r.GOODS_NO
    LEFT JOIN PR_GOODS_DSCNT_PRC_INFO d ON g.GOODS_NO = d.GOODS_NO
    WHERE r.FST_DISP_YN = 'Y'
    ORDER BY RCMD_SCR DESC NULLS LAST
    FETCH FIRST :limit ROWS ONLY
""")

# 2. 최고 할인율: EXTRA_FVR_SALE_PER 높은 순
DISCOUNT_SQL = text("""
    SELECT g.GOODS_NO,
           g.GOODS_NM,
           d.EXTRA_FVR_SALE_PRC,
           d.EXTRA_FVR_SALE_PER,
           NULL AS RCMD_SCR,
           r.T_COMFORT,
           r.T_SILENCE,
           r.T_LIFE_SPAN,
           r.T_FUEL_EFF_CONVERT
    FROM PR_GOODS_BASE g
    JOIN PR_GOODS_DSCNT_PRC_INFO d   ON g.GOODS_NO = d.GOODS_NO
    LEFT JOIN PR_GOODS_RCMD_SUM r    ON g.GOODS_NO = r.GOODS_NO
    ORDER BY d.EXTRA_FVR_SALE_PER DESC NULLS LAST
    FETCH FIRST :limit ROWS ONLY
""")

# 3. 가성비 Good: 할인가 20만원 이하, 수명·연비 높은 순
VALUE_SQL = text("""
    SELECT g.GOODS_NO,
           g.GOODS_NM,
           d.EXTRA_FVR_SALE_PRC,
           d.EXTRA_FVR_SALE_PER,
           NULL AS RCMD_SCR,
           r.T_COMFORT,
           r.T_SILENCE,
           r.T_LIFE_SPAN,
           r.T_FUEL_EFF_CONVERT
    FROM PR_GOODS_BASE g
    JOIN PR_GOODS_DSCNT_PRC_INFO d   ON g.GOODS_NO = d.GOODS_NO
    LEFT JOIN PR_GOODS_RCMD_SUM r    ON g.GOODS_NO = r.GOODS_NO
    WHERE d.EXTRA_FVR_SALE_PRC <= :price_limit
    ORDER BY r.T_LIFE_SPAN DESC NULLS LAST, r.T_FUEL_EFF_CONVERT DESC NULLS LAST
    FETCH FIRST :limit ROWS ONLY
""")

_SQL_MAP = {
    RcmdType.tstation: TSTATION_SQL,
    RcmdType.discount: DISCOUNT_SQL,
    RcmdType.value: VALUE_SQL,
}


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.get(
    "",
    response_model=RecommendationResponse,
    summary="상품 추천",
    description=(
        "추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.\n\n"
        "- **tstation**: 티스테이션 추천 (`FST_DISP_YN='Y'`, `TOT_SCR*10` 높은 순, `PR_GOODS_RCMD_SUM`)\n"
        "- **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)\n"
        "- **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)"
    ),
)
async def get_recommendations(
    rcmd_type: RcmdType = Query(..., description="추천 타입 (tstation | discount | value)"),
    limit: int = Query(10, ge=1, le=100, description="반환할 상품 수 (기본 10, 최대 100)"),
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:

    params: dict = {"limit": limit}
    if rcmd_type == RcmdType.value:
        params["price_limit"] = _VALUE_PRICE_LIMIT

    rows = (
        await db.execute(_SQL_MAP[rcmd_type], params)
    ).mappings().all()

    items = [
        RcmdGoodsItem(
            goods_no=str(r["goods_no"]),
            goods_nm=r["goods_nm"],
            extra_fvr_sale_prc=int(r["extra_fvr_sale_prc"]) if r["extra_fvr_sale_prc"] is not None else None,
            extra_fvr_sale_per=float(r["extra_fvr_sale_per"]) if r["extra_fvr_sale_per"] is not None else None,
            rcmd_scr=float(r["rcmd_scr"]) if r["rcmd_scr"] is not None else None,
            t_comfort=float(r["t_comfort"]) if r["t_comfort"] is not None else None,
            t_silence=float(r["t_silence"]) if r["t_silence"] is not None else None,
            t_life_span=float(r["t_life_span"]) if r["t_life_span"] is not None else None,
            t_fuel_eff_convert=float(r["t_fuel_eff_convert"]) if r["t_fuel_eff_convert"] is not None else None,
        )
        for r in rows
    ]

    return RecommendationResponse(
        rcmd_type=rcmd_type.value,
        total=len(items),
        items=items,
    )
