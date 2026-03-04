from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas import ProductDescResponse, ProductImage

router = APIRouter(
    prefix="/api/descriptions",
    tags=["Product Description AF - 상품 설명"],
)


# --------------------------------------------------------------------------- #
#  SQL 상수                                                                     #
# --------------------------------------------------------------------------- #

# 상품 패턴 텍스트 조회: PR_GOODS_BASE → PR_PATTERN_BASE (PTRN_NO 조인)
DESC_TEXT_SQL = text("""
    SELECT p.PTRN_NO,
           p.PC_PROD_REMARK_DESC,
           p.PC_PROD_TECH_DESC,
           p.SLOGAN
    FROM PR_GOODS_BASE g
    JOIN PR_PATTERN_BASE p ON g.PTRN_NO = p.PTRN_NO
    WHERE g.GOODS_NO = :goods_no
""")

# 패턴 이미지 목록 조회: PR_PTRN_IMG_INFO (PTRN_NO 기준, 등록 순)
DESC_IMG_SQL = text("""
    SELECT IMG_PATH_NM, THNL_PATH_NM
    FROM PR_PTRN_IMG_INFO
    WHERE PTRN_NO = :ptrn_no
    ORDER BY SORT_ORD ASC NULLS LAST
""")


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.get(
    "/{goods_no}",
    response_model=ProductDescResponse,
    summary="상품 설명 조회",
    description=(
        "상품 번호로 PR_GOODS_BASE → PR_PATTERN_BASE를 조인하여 "
        "특장점(PC_PROD_REMARK_DESC), 기술력(PC_PROD_TECH_DESC), 슬로건(SLOGAN)을 조회하고, "
        "PR_PTRN_IMG_INFO에서 이미지 및 썸네일 경로 목록을 반환합니다."
    ),
)
async def get_description(
    goods_no: str,
    db: AsyncSession = Depends(get_db),
) -> ProductDescResponse:

    # ── 1. 텍스트 설명 조회 ──────────────────────────────────────────────────
    text_row = (
        await db.execute(DESC_TEXT_SQL, {"goods_no": goods_no})
    ).mappings().first()

    if text_row is None:
        raise HTTPException(status_code=404, detail=f"상품 설명을 찾을 수 없습니다: {goods_no}")

    ptrn_no = str(text_row["ptrn_no"]) if text_row["ptrn_no"] is not None else None

    # ── 2. 이미지 목록 조회 ──────────────────────────────────────────────────
    images: list[ProductImage] = []
    if ptrn_no:
        img_rows = (
            await db.execute(DESC_IMG_SQL, {"ptrn_no": ptrn_no})
        ).mappings().all()

        images = [
            ProductImage(
                img_path_nm=r["img_path_nm"],
                thnl_path_nm=r["thnl_path_nm"],
            )
            for r in img_rows
        ]

    return ProductDescResponse(
        goods_no=goods_no,
        ptrn_no=ptrn_no,
        pc_prod_remark_desc=text_row["pc_prod_remark_desc"],
        pc_prod_tech_desc=text_row["pc_prod_tech_desc"],
        slogan=text_row["slogan"],
        images=images,
    )
