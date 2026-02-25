import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas import InventoryResponse, ShopStockInfo

router = APIRouter(prefix="/api/inventory", tags=["Inventory AF - 재고 조회"])

# 외부 API (티스테이션) 기본 URL - 환경변수로 설정
_TSTATION_API_URL = os.getenv("TSTATION_API_URL", "http://tstation-api/")


# --------------------------------------------------------------------------- #
#  SQL 상수                                                                     #
# --------------------------------------------------------------------------- #

# 물류 재고: 오라클 함수 FN_GET_GOODS_STOCK_QTY 호출
LOGISTICS_STOCK_SQL = text("""
    SELECT FN_GET_GOODS_STOCK_QTY(:goods_no) AS STOCK_QTY FROM DUAL
""")

# MD 재고 (참고용)
MD_STOCK_SQL = text("""
    SELECT INV_QTY
    FROM INV_GOODS_INFO
    WHERE GOODS_NO = :goods_no
""")


# --------------------------------------------------------------------------- #
#  외부 API 호출 (TSN00590 인터페이스)                                           #
# --------------------------------------------------------------------------- #

async def _fetch_shop_stock(goods_no: str, shop_id: str) -> ShopStockInfo:
    """티스테이션 외부 API를 호출하여 매장 재고(오늘서비스/바로배송)를 조회합니다.

    인터페이스 규격: TSN00590
    """
    url = f"{_TSTATION_API_URL.rstrip('/')}/api/stock/shop"
    payload = {"goods_no": goods_no, "shop_id": shop_id}

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    return ShopStockInfo(
        today_service_qty=data.get("today_service_qty"),
        direct_delivery_qty=data.get("direct_delivery_qty"),
    )


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.get(
    "/{goods_no}",
    response_model=InventoryResponse,
    summary="상품 재고 조회",
    description=(
        "물류 재고(오라클 함수 FN_GET_GOODS_STOCK_QTY)와 "
        "매장 재고(오늘서비스/바로배송, 외부 TSN00590 API)를 함께 반환합니다. "
        "MD 재고(INV_QTY)는 참고용으로 포함됩니다."
    ),
)
async def get_inventory(
    goods_no: str,
    shop_id: str = Query(..., description="매장 ID"),
    db: AsyncSession = Depends(get_db),
) -> InventoryResponse:

    # ── 1. 물류 재고: 오라클 함수 호출 ─────────────────────────────────────
    logistics_row = (
        await db.execute(LOGISTICS_STOCK_SQL, {"goods_no": goods_no})
    ).mappings().first()

    logistics_qty: Optional[int] = (
        int(logistics_row["stock_qty"])
        if logistics_row and logistics_row["stock_qty"] is not None
        else None
    )

    # ── 2. MD 재고 (참고용) ─────────────────────────────────────────────────
    # md_row = (
    #     await db.execute(MD_STOCK_SQL, {"goods_no": goods_no})
    # ).mappings().first()

    # md_inv_qty: Optional[int] = (
    #     int(md_row["inv_qty"])
    #     if md_row and md_row["inv_qty"] is not None
    #     else None
    # )

    # ── 3. 매장 재고: 외부 API 호출 (TSN00590) ──────────────────────────────
    try:
        shop_stock = await _fetch_shop_stock(goods_no, shop_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"매장 재고 API 오류: {e.response.status_code}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"매장 재고 API 연결 실패: {e}",
        )

    return InventoryResponse(
        goods_no=goods_no,
        shop_id=shop_id,
        logistics_qty=logistics_qty,
        shop_stock=shop_stock,
        # md_inv_qty=md_inv_qty,
        md_inv_qty=0,
    )
