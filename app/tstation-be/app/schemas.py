from pydantic import BaseModel, Field
from typing import Optional


class TimeSlot(BaseModel):
    tm: str = Field(..., description="예약 가능 시간 슬롯 (예: '0900', '1030')")


class ShopItem(BaseModel):
    shop_id: str = Field(..., description="매장 ID")
    shop_seq: Optional[str] = Field(None, description="매장 순번")
    shop_nm: Optional[str] = Field(None, description="매장명")
    addr_base: Optional[str] = Field(None, description="지번주소")
    road_addr_base: Optional[str] = Field(None, description="도로명주소")
    shop_tel_no: Optional[str] = Field(None, description="전화번호")
    shop_biz_strt_time: Optional[str] = Field(None, description="영업 시작 시간")
    shop_biz_end_time: Optional[str] = Field(None, description="영업 종료 시간")
    shop_hldd: Optional[str] = Field(None, description="휴무일")
    shop_xpos: Optional[float] = Field(None, description="매장 X 좌표")
    shop_ypos: Optional[float] = Field(None, description="매장 Y 좌표")
    distance: Optional[float] = Field(None, description="고객 위치와의 거리 (좌표 기준)")
    available_times: list[TimeSlot] = Field(default_factory=list, description="예약 가능 시간 슬롯 목록")
    images: list[str] = Field(default_factory=list, description="매장 이미지 경로 목록")


class ShopListResponse(BaseModel):
    total: int = Field(..., description="조회된 매장 수")
    cal_day: str = Field(..., description="조회 기준 날짜 (YYYYMMDD)")
    shops: list[ShopItem]


# --------------------------------------------------------------------------- #
#  Price AF 스키마                                                              #
# --------------------------------------------------------------------------- #

class PriceResponse(BaseModel):
    goods_id: str = Field(..., description="상품 ID")
    # 판매가 (PR_ITEM_PRC_INFO)
    sale_prc: Optional[int] = Field(None, description="기본 판매가")
    # 혜택가 (PR_GOODS_DSCNT_PRC_INFO)
    extra_fvr_sale_prc: Optional[int] = Field(None, description="최대 혜택 판매가 (쿠폰 등 적용)")
    extra_fvr_sale_per: Optional[float] = Field(None, description="최대 혜택 할인율 (%)")
    # 공임비 (PR_GOODS_BASE)
    wage_prc: Optional[int] = Field(None, description="공임비")
    wage_today_prc: Optional[int] = Field(None, description="오늘의 공임비")