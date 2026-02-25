from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas import OrderDeliveryResponse, ORD_STAT_LABEL, DLV_STAT_LABEL

router = APIRouter(prefix="/api/orders", tags=["Order/Delivery AF - 주문 및 배송 추적"])


# --------------------------------------------------------------------------- #
#  SQL 상수                                                                     #
# --------------------------------------------------------------------------- #

# 주문 진행 상태 (OP_ORD_DTL_INFO)
ORDER_SQL = text("""
    SELECT ORD_NO, ORD_PRGS_STAT_CD
    FROM OP_ORD_DTL_INFO
    WHERE ORD_NO = :ord_no
""")

# 배송 진행 상태 + 배송 정보 (OP_ORD_DLV_DTL_INFO)
DELIVERY_SQL = text("""
    SELECT DLV_PRGS_STAT_CD, INV_NO, HDC_CD, DLV_FCST_DTIME
    FROM OP_ORD_DLV_DTL_INFO
    WHERE ORD_NO = :ord_no
""")


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.get(
    "/{ord_no}",
    response_model=OrderDeliveryResponse,
    summary="주문 및 배송 상태 조회",
    description=(
        "주문 번호로 주문 진행 상태(OP_ORD_DTL_INFO)와 "
        "배송 진행 상태·운송장 정보(OP_ORD_DLV_DTL_INFO)를 함께 반환합니다."
    ),
)
async def get_order_delivery(
    ord_no: str,
    db: AsyncSession = Depends(get_db),
) -> OrderDeliveryResponse:

    # ── 1. 주문 상태 조회 ────────────────────────────────────────────────────
    ord_row = (
        await db.execute(ORDER_SQL, {"ord_no": ord_no})
    ).mappings().first()

    if ord_row is None:
        raise HTTPException(status_code=404, detail=f"주문을 찾을 수 없습니다: {ord_no}")

    ord_stat_cd = str(ord_row["ord_prgs_stat_cd"]) if ord_row["ord_prgs_stat_cd"] is not None else None

    # ── 2. 배송 상태 조회 ────────────────────────────────────────────────────
    dlv_row = (
        await db.execute(DELIVERY_SQL, {"ord_no": ord_no})
    ).mappings().first()

    dlv_stat_cd = None
    inv_no = None
    hdc_cd = None
    dlv_fcst_dtime = None

    if dlv_row is not None:
        dlv_stat_cd = str(dlv_row["dlv_prgs_stat_cd"]) if dlv_row["dlv_prgs_stat_cd"] is not None else None
        inv_no = dlv_row["inv_no"]
        hdc_cd = dlv_row["hdc_cd"]
        dlv_fcst_dtime = str(dlv_row["dlv_fcst_dtime"]) if dlv_row["dlv_fcst_dtime"] is not None else None

    return OrderDeliveryResponse(
        ord_no=ord_no,
        ord_prgs_stat_cd=ord_stat_cd,
        ord_prgs_stat_nm=ORD_STAT_LABEL.get(ord_stat_cd) if ord_stat_cd else None,
        dlv_prgs_stat_cd=dlv_stat_cd,
        dlv_prgs_stat_nm=DLV_STAT_LABEL.get(dlv_stat_cd) if dlv_stat_cd else None,
        inv_no=inv_no,
        hdc_cd=hdc_cd,
        dlv_fcst_dtime=dlv_fcst_dtime,
    )
