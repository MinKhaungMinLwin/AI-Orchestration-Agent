from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas import PriceResponse

router = APIRouter(prefix="/api/prices", tags=["Price AF - 가격 및 할인 조회"])


# --------------------------------------------------------------------------- #
#  SQL 상수                                                                     #
# --------------------------------------------------------------------------- #

# 판매가 + 혜택가 + 공임비를 GOODS_NO 기준으로 LEFT JOIN 조회
PRICE_SQL = text("""
    SELECT
        p.SALE_PRC,
        d.EXTRA_FVR_SALE_PRC,
        d.EXTRA_FVR_SALE_PER,
        b.WAGE_PRC,
        b.WAGE_TODAY_PRC
    FROM PR_ITEM_PRC_INFO p
    LEFT JOIN PR_GOODS_DSCNT_PRC_INFO d ON p.GOODS_NO = d.GOODS_NO
    LEFT JOIN PR_GOODS_BASE b           ON p.GOODS_NO = b.GOODS_NO
    WHERE p.GOODS_NO = :goods_no
""")


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.get(
    "/{goods_no}",
    response_model=PriceResponse,
    summary="상품 가격 및 할인 조회",
    description=(
        "상품 번호로 기본 판매가, 최대 혜택가(프로모션·쿠폰 적용), "
        "공임비 및 오늘의 공임비를 반환합니다.\n(샘플번호: G000000314254)"
    ),
)
async def get_price(
    goods_no: str,
    db: AsyncSession = Depends(get_db),
) -> PriceResponse:
    row = (
        await db.execute(PRICE_SQL, {"goods_no": goods_no})
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {goods_no}")

    return PriceResponse(
        goods_id=goods_no,
        sale_prc=row["sale_prc"],
        extra_fvr_sale_prc=row["extra_fvr_sale_prc"],
        extra_fvr_sale_per=row["extra_fvr_sale_per"],
        wage_prc=row["wage_prc"],
        wage_today_prc=row["wage_today_prc"],
    )