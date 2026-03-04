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

# --------------------------------------------------------------------------- #
#  Inventory AF 스키마                                                          #
# --------------------------------------------------------------------------- #

class ShopStockInfo(BaseModel):
    today_service_qty: Optional[int] = Field(None, description="오늘서비스 가용 재고 수량")
    direct_delivery_qty: Optional[int] = Field(None, description="바로배송 가용 재고 수량")


class InventoryResponse(BaseModel):
    goods_no: str = Field(..., description="상품 번호")
    shop_id: str = Field(..., description="매장 ID")
    logistics_qty: Optional[int] = Field(None, description="물류 재고 수량 (FN_GET_GOODS_STOCK_QTY)")
    shop_stock: ShopStockInfo = Field(default_factory=ShopStockInfo, description="매장 재고 (오늘서비스/바로배송)")
    md_inv_qty: Optional[int] = Field(None, description="MD 재고 수량 (참고용)")


# --------------------------------------------------------------------------- #
#  Order / Delivery AF 스키마                                                   #
# --------------------------------------------------------------------------- #

# 주문 진행 상태 코드 → 한글명
ORD_STAT_LABEL: dict[str, str] = {
    "10": "주문접수",
    "20": "주문완료",
    "40": "출하지시",
    "50": "출고완료",
    "60": "배송완료",
    "70": "장착완료",
    "99": "배송취소",
}

# 배송 진행 상태 코드 → 한글명
DLV_STAT_LABEL: dict[str, str] = {
    "10": "주문접수",
    "20": "주문완료",
    "40": "배송준비중",
    "50": "배송중",
    "60": "배송완료",
    "70": "장착완료",
    "99": "배송취소",
}


class OrderDeliveryResponse(BaseModel):
    ord_no: str = Field(..., description="주문 번호")
    # 주문 상태
    ord_prgs_stat_cd: Optional[str] = Field(None, description="주문 진행 상태 코드")
    ord_prgs_stat_nm: Optional[str] = Field(None, description="주문 진행 상태명")
    # 배송 상태
    dlv_prgs_stat_cd: Optional[str] = Field(None, description="배송 진행 상태 코드")
    dlv_prgs_stat_nm: Optional[str] = Field(None, description="배송 진행 상태명")
    # 배송 정보
    inv_no: Optional[str] = Field(None, description="운송장 번호")
    hdc_cd: Optional[str] = Field(None, description="택배사 코드")
    dlv_fcst_dtime: Optional[str] = Field(None, description="도착 예정 일시")


# --------------------------------------------------------------------------- #
#  Quick Shopping AF 스키마                                                    #
# --------------------------------------------------------------------------- #

class QuickOrderRequest(BaseModel):
    mbr_no: Optional[str] = Field(None, description="회원 번호 (MBR_NO 또는 CAR_NO 중 하나 필수)")
    car_no: Optional[str] = Field(None, description="차량 번호 (MBR_NO 또는 CAR_NO 중 하나 필수)")
    goods_no: str = Field(..., description="상품 번호")
    ord_qty: int = Field(..., ge=1, description="주문 수량")


class QuickOrderResponse(BaseModel):
    redirect_url: str = Field(..., description="주문서 작성 페이지 URL")


# --------------------------------------------------------------------------- #
#  Product Compatibility AF 스키마                                             #
# --------------------------------------------------------------------------- #

class TireSpec(BaseModel):
    tire_width: Optional[int] = Field(None, description="단면폭 (TIRE_WIDTH)")
    tire_series: Optional[int] = Field(None, description="편평비 (TIRE_SERIES)")
    inch: Optional[int] = Field(None, description="인치 (INCH)")


class CompatibilityResponse(BaseModel):
    car_no: str = Field(..., description="차량 번호")
    goods_no: str = Field(..., description="상품 번호")
    # 차량 타이어 사이즈 (원본값)
    tire_size_fr: Optional[str] = Field(None, description="차량 전륜 타이어 사이즈 (예: 205/55R16)")
    tire_size_re: Optional[str] = Field(None, description="차량 후륜 타이어 사이즈 (예: 225/45R17)")
    # 상품 타이어 스펙
    goods_spec: TireSpec = Field(default_factory=TireSpec, description="상품 타이어 스펙 (단면폭/편평비/인치)")
    # 호환 여부
    is_compatible_fr: bool = Field(..., description="전륜 호환 여부")
    is_compatible_re: bool = Field(..., description="후륜 호환 여부")
    is_compatible: bool = Field(..., description="전체 호환 여부 (전/후 모두 호환 시 true)")


# --------------------------------------------------------------------------- #
#  Product Recommendation AF 스키마                                            #
# --------------------------------------------------------------------------- #

class RcmdGoodsItem(BaseModel):
    goods_no: str = Field(..., description="상품 번호")
    goods_nm: Optional[str] = Field(None, description="상품명")
    # 할인 정보
    extra_fvr_sale_prc: Optional[int] = Field(None, description="최대 혜택 판매가")
    extra_fvr_sale_per: Optional[float] = Field(None, description="최대 혜택 할인율 (%)")
    # 추천 점수 (티스테이션 추천 타입만 반환)
    rcmd_scr: Optional[float] = Field(None, description="추천 점수 (TOT_SCR * 10, 티스테이션 추천 전용)")
    # 성향 지표
    t_comfort: Optional[float] = Field(None, description="승차감 (T_COMFORT)")
    t_silence: Optional[float] = Field(None, description="정숙성 (T_SILENCE)")
    t_life_span: Optional[float] = Field(None, description="수명 (T_LIFE_SPAN)")
    t_fuel_eff_convert: Optional[float] = Field(None, description="연비 (T_FUEL_EFF_CONVERT)")


class RecommendationResponse(BaseModel):
    rcmd_type: str = Field(..., description="추천 타입 (tstation | discount | value)")
    total: int = Field(..., description="반환된 상품 수")
    items: list[RcmdGoodsItem]


# --------------------------------------------------------------------------- #
#  Product Description AF 스키마                                               #
# --------------------------------------------------------------------------- #

class ProductImage(BaseModel):
    img_path_nm: Optional[str] = Field(None, description="이미지 경로 (IMG_PATH_NM)")
    thnl_path_nm: Optional[str] = Field(None, description="썸네일 경로 (THNL_PATH_NM)")


class ProductDescResponse(BaseModel):
    goods_no: str = Field(..., description="상품 번호")
    ptrn_no: Optional[str] = Field(None, description="패턴 번호")
    # 텍스트 설명
    pc_prod_remark_desc: Optional[str] = Field(None, description="특장점 (PC_PROD_REMARK_DESC)")
    pc_prod_tech_desc: Optional[str] = Field(None, description="기술력 (PC_PROD_TECH_DESC)")
    slogan: Optional[str] = Field(None, description="슬로건 (SLOGAN)")
    # 이미지 목록
    images: list[ProductImage] = Field(default_factory=list, description="상품 이미지 목록")


# --------------------------------------------------------------------------- #
#  FAQ AF 스키마                                                                #
# --------------------------------------------------------------------------- #

class FaqItem(BaseModel):
    lrcl_cd: Optional[str] = Field(None, description="대분류 코드 (LRCL_CD)")
    mdcl_cd: Optional[str] = Field(None, description="중분류 코드 (MDCL_CD)")
    cust_quest: Optional[str] = Field(None, description="질문 (CUST_QUEST)")
    pc_ans_cont: Optional[str] = Field(None, description="답변 (PC_ANS_CONT)")


class FaqListResponse(BaseModel):
    total: int = Field(..., description="반환된 FAQ 수")
    items: list[FaqItem]


# --------------------------------------------------------------------------- #
#  Fallback / Escalation AF 스키마                                             #
# --------------------------------------------------------------------------- #

class EscalationRequest(BaseModel):
    mbr_no: Optional[str] = Field(None, description="회원 번호 (상담 페이지 전달용)")
    inq_type_cd: Optional[str] = Field(None, description="문의 유형 코드 (정책 기반 채널 분기에 사용)")
    msg_count: int = Field(0, ge=0, description="현재까지의 대화 메시지 수")
    summary: Optional[str] = Field(None, description="AI가 생성한 대화 요약 (대화량 충분 시 전달)")


class EscalationResponse(BaseModel):
    channel: str = Field(..., description="상담 채널 (chat | call | email)")
    branch: str = Field(..., description="분기 유형 (with_summary | direct | policy)")
    has_summary: bool = Field(..., description="요약 내용 포함 여부")
    redirect_url: str = Field(..., description="상담 페이지 URL (요약은 summary 쿼리 파라미터로 전달)")


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