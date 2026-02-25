from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas import FaqListResponse, FaqItem

router = APIRouter(
    prefix="/api/faq",
    tags=["FAQ AF - 일반 문의"],
)

# 개인정보 보호: 1:1 문의를 제외한 FAQ 유형 코드
_FAQ_TYPE_CD = "FAQ"


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.get(
    "",
    response_model=FaqListResponse,
    summary="FAQ 목록 조회",
    description=(
        "CS_CUST_INQ_MGMT_INFO에서 FAQ 데이터(INQ_TYPE_CD='FAQ')만 조회합니다. "
        "1:1 문의 내역은 개인정보 보호를 위해 제외됩니다. "
        "lrcl_cd(대분류), mdcl_cd(중분류)로 필터링할 수 있습니다."
    ),
)
async def get_faq(
    lrcl_cd: Optional[str] = Query(None, description="대분류 코드 필터 (LRCL_CD)"),
    mdcl_cd: Optional[str] = Query(None, description="중분류 코드 필터 (MDCL_CD)"),
    limit: int = Query(50, ge=1, le=200, description="반환할 FAQ 수 (기본 50, 최대 200)"),
    db: AsyncSession = Depends(get_db),
) -> FaqListResponse:

    # ── WHERE 절 동적 구성 ────────────────────────────────────────────────────
    conditions = ["INQ_TYPE_CD = :faq_type_cd"]
    params: dict = {"faq_type_cd": _FAQ_TYPE_CD, "limit": limit}

    if lrcl_cd:
        conditions.append("LRCL_CD = :lrcl_cd")
        params["lrcl_cd"] = lrcl_cd

    if mdcl_cd:
        conditions.append("MDCL_CD = :mdcl_cd")
        params["mdcl_cd"] = mdcl_cd

    where_clause = " AND ".join(conditions)

    sql = text(f"""
        SELECT LRCL_CD, MDCL_CD, CUST_QUEST, PC_ANS_CONT
        FROM CS_CUST_INQ_MGMT_INFO
        WHERE {where_clause}
        ORDER BY LRCL_CD ASC NULLS LAST, MDCL_CD ASC NULLS LAST
        FETCH FIRST :limit ROWS ONLY
    """)

    rows = (
        await db.execute(sql, params)
    ).mappings().all()

    items = [
        FaqItem(
            lrcl_cd=r["lrcl_cd"],
            mdcl_cd=r["mdcl_cd"],
            cust_quest=r["cust_quest"],
            pc_ans_cont=r["pc_ans_cont"],
        )
        for r in rows
    ]

    return FaqListResponse(total=len(items), items=items)
