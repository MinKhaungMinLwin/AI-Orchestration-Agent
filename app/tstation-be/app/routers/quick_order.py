import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas import QuickOrderRequest, QuickOrderResponse

router = APIRouter(prefix="/api/quick-order", tags=["Quick Shopping AF - 퀵 쇼핑/주문서 초안 생성"])

# 주문서 작성 페이지 베이스 URL - 환경변수로 설정
_QUICK_ORDER_BASE_URL = os.getenv("QUICK_ORDER_BASE_URL", "http://shop.example.com")

# 판매 가능 상태 코드 (PRGS_STAT_CD)
_SALE_ACTIVE_CD = "10"


# --------------------------------------------------------------------------- #
#  SQL 상수                                                                     #
# --------------------------------------------------------------------------- #

# PR_GOODS_BASE 상품 유효성 검증
GOODS_VALID_SQL = text("""
    SELECT PRGS_STAT_CD, ORD_PSB_MIN_QTY
    FROM PR_GOODS_BASE
    WHERE GOODS_NO = :goods_no
""")


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.post(
    "",
    response_model=QuickOrderResponse,
    summary="퀵 쇼핑 / 주문서 초안 생성",
    description=(
        "회원번호(MBR_NO) 또는 차량번호(CAR_NO)와 상품번호(GOODS_NO), 수량(ORD_QTY)을 입력받아 "
        "상품 유효성(PR_GOODS_BASE: 판매 상태, 최소 주문 수량)을 검증한 뒤, "
        "주문서 작성 페이지 URL(REDIRECT_URL)을 반환합니다."
    ),
)
async def create_quick_order(
    body: QuickOrderRequest,
    db: AsyncSession = Depends(get_db),
) -> QuickOrderResponse:

    # ── 1. MBR_NO / CAR_NO 중 하나는 필수 ────────────────────────────────────
    if not body.mbr_no and not body.car_no:
        raise HTTPException(status_code=422, detail="MBR_NO 또는 CAR_NO 중 하나는 필수입니다.")

    # ── 2. 상품 유효성 검증 (PR_GOODS_BASE) ──────────────────────────────────
    row = (
        await db.execute(GOODS_VALID_SQL, {"goods_no": body.goods_no})
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {body.goods_no}")

    prgs_stat_cd = str(row["prgs_stat_cd"]) if row["prgs_stat_cd"] is not None else None
    if prgs_stat_cd != _SALE_ACTIVE_CD:
        raise HTTPException(
            status_code=422,
            detail=f"판매 중인 상품이 아닙니다. (PRGS_STAT_CD={prgs_stat_cd})",
        )

    ord_psb_min_qty = int(row["ord_psb_min_qty"]) if row["ord_psb_min_qty"] is not None else 1
    if body.ord_qty < ord_psb_min_qty:
        raise HTTPException(
            status_code=422,
            detail=f"주문 수량({body.ord_qty})이 최소 주문 수량({ord_psb_min_qty})보다 적습니다.",
        )

    # ── 3. 주문서 URL 생성 ────────────────────────────────────────────────────
    base = _QUICK_ORDER_BASE_URL.rstrip("/")
    params = f"goods_no={body.goods_no}&ord_qty={body.ord_qty}"
    if body.mbr_no:
        params += f"&mbr_no={body.mbr_no}"
    if body.car_no:
        params += f"&car_no={body.car_no}"

    redirect_url = f"{base}/order/quick?{params}"

    return QuickOrderResponse(redirect_url=redirect_url)
