from datetime import date
from typing import Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, bindparam

from app.database import get_db
from app.schemas import ShopItem, ShopListResponse, TimeSlot

router = APIRouter(prefix="/api/shops", tags=["Store AF - 매장 정보 및 예약 조회"])


# --------------------------------------------------------------------------- #
#  SQL 상수                                                                     #
# --------------------------------------------------------------------------- #

# 매장 기본 정보 + 거리 계산 (유클리드 거리)
SHOP_LIST_SQL = text("""
    SELECT
        SHOP_ID,
        SHOP_SEQ,
        SHOP_NM,
        ADDR_BASE,
        ROAD_ADDR_BASE,
        SHOP_TEL_NO,
        SHOP_BIZ_STRT_TIME,
        SHOP_BIZ_END_TIME,
        SHOP_HLDD,
        SHOP_XPOS,
        SHOP_YPOS,
        SQRT(
            POWER(SHOP_XPOS - :user_xpos, 2) +
            POWER(SHOP_YPOS - :user_ypos, 2)
        ) AS DISTANCE
    FROM VW_ET_SHOP_INFO
    WHERE SHOP_XPOS IS NOT NULL
      AND SHOP_YPOS IS NOT NULL
    ORDER BY DISTANCE
    FETCH FIRST :limit ROWS ONLY
""")

# 예약 가능 시간 슬롯 (다수 매장 일괄 조회)
TIME_SLOTS_SQL = text("""
    SELECT SHOP_ID, CAL_DAY || TM as TM
    FROM VI_SHOP_OPEN_DT
    WHERE SHOP_ID IN :shop_ids
    ORDER BY SHOP_ID, TM
""").bindparams(bindparam("shop_ids", expanding=True))

# 매장 이미지 (다수 매장 일괄 조회)
IMAGES_SQL = text("""
    SELECT SHOP_SEQ as SHOP_ID, SHOP_IMG_PATH
    FROM ET_SHOP_IMG_INFO
    WHERE SHOP_SEQ IN :shop_ids
    ORDER BY SHOP_ID
""").bindparams(bindparam("shop_ids", expanding=True))


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.get(
    "",
    response_model=ShopListResponse,
    summary="주변 매장 조회 및 예약 가능 시간 확인",
    description=(
        "고객의 현재 위치(X, Y 좌표)를 기반으로 가까운 매장을 추천하고, (예 126.92344, 37.61624)"
        "지정 날짜의 예약 가능 시간 슬롯과 매장 이미지를 함께 반환합니다."
    ),
)
async def get_nearby_shops(
    user_xpos: float = Query(..., description="고객 현재 X 좌표"),
    user_ypos: float = Query(..., description="고객 현재 Y 좌표"),
    cal_day: Optional[str] = Query(
        None,
        description="예약 조회 날짜 (YYYYMMDD). 미입력 시 오늘 날짜 사용",
        pattern=r"^\d{8}$",
    ),
    limit: int = Query(1, ge=1, le=50, description="반환할 최대 매장 수"),
    db: AsyncSession = Depends(get_db),
) -> ShopListResponse:
    target_day = cal_day or date.today().strftime("%Y%m%d")

    # ── 1. 매장 기본 정보 조회 ──────────────────────────────────────────────
    rows = (
        await db.execute(
            SHOP_LIST_SQL,
            {"user_xpos": user_xpos, "user_ypos": user_ypos, "limit": limit},
        )
    ).mappings().all()

    if not rows:
        return ShopListResponse(total=0, cal_day=target_day, shops=[])

    print(rows)
    shop_ids = [r["shop_id"] for r in rows]

    # ── 2. 예약 가능 시간 슬롯 일괄 조회 ───────────────────────────────────
    time_rows = (
        await db.execute(
            TIME_SLOTS_SQL,
            {"shop_ids": shop_ids, "cal_day": target_day},
        )
    ).mappings().all()

    times_by_shop: dict[str, list[TimeSlot]] = defaultdict(list)
    for t in time_rows:
        times_by_shop[t["shop_id"]].append(TimeSlot(tm=str(t["tm"])))

    # ── 3. 매장 이미지 일괄 조회 ────────────────────────────────────────────
    img_rows = (
        await db.execute(
            IMAGES_SQL,
            {"shop_ids": shop_ids},
        )
    ).mappings().all()

    # 현재 매장 수는 4,075개 이미지 개수는 421개
    images_by_shop: dict[str, list[str]] = defaultdict(list)
    for img in img_rows:
        if img["shop_img_path"]:
            images_by_shop[img["shop_id"]].append(img["shop_img_path"])

    # ── 4. 결과 조합 ────────────────────────────────────────────────────────
    shops = [
        ShopItem(
            shop_id=r["shop_id"],
            shop_seq=r["shop_seq"],
            shop_nm=r["shop_nm"],
            addr_base=r["addr_base"],
            road_addr_base=r["road_addr_base"],
            shop_tel_no=r["shop_tel_no"],
            shop_biz_strt_time=r["shop_biz_strt_time"],
            shop_biz_end_time=r["shop_biz_end_time"],
            shop_hldd=r["shop_hldd"],
            shop_xpos=r["shop_xpos"],
            shop_ypos=r["shop_ypos"],
            distance=float(r["distance"]) if r["distance"] is not None else None,
            available_times=times_by_shop[r["shop_id"]],
            # images=[]
            images=images_by_shop[r["shop_id"]],
        )
        for r in rows
    ]

    return ShopListResponse(total=len(shops), cal_day=target_day, shops=shops)