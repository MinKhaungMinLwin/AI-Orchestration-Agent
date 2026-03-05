from langchain.tools import tool

# ==========================================
# MOCK FAQ DATABASE – T-STATION (CS_CUST_INQ_MGMT_INFO)
# ==========================================

MOCK_FAQ_DB = [
    # ---------------------------------------------------------
    # Category: Reservation (01)
    # ---------------------------------------------------------
    {
        "faq_id": "FAQ001_EN",
        "CUST_QUEST": "How do I cancel or change my tire installation appointment?",
        "PC_ANS_CONT": "You can cancel or change your appointment by navigating to 'My Page' > 'Order/Reservation History'. Changes must be made at least 24 hours prior to your scheduled time. If it is within 24 hours, please contact the specific T-Station store directly.",
        "LRCL_CD": "01", # Large Category: Reservation
        "MDCL_CD": "01"  # Medium Category: Change/Cancel
    },
    {
        "faq_id": "FAQ001_KO",
        "CUST_QUEST": "타이어 장착 예약을 취소하거나 변경하려면 어떻게 해야 하나요?",
        "PC_ANS_CONT": "예약 취소 및 변경은 '마이페이지' > '주문/예약 내역'에서 가능합니다. 예약 변경 및 취소는 예정된 시간으로부터 최소 24시간 전까지 가능합니다. 24시간 이내인 경우 해당 티스테이션 매장으로 직접 문의해 주시기 바랍니다.",
        "LRCL_CD": "01",
        "MDCL_CD": "01" 
    },

    # ---------------------------------------------------------
    # Category: Returns/Refunds (02)
    # ---------------------------------------------------------
    {
        "faq_id": "FAQ002_EN",
        "CUST_QUEST": "Can I return tires after they have been installed?",
        "PC_ANS_CONT": "Once tires have been mounted on your vehicle and driven, they cannot be returned unless there is a verifiable manufacturing defect. Please inspect your tires before installation.",
        "LRCL_CD": "02", # Large Category: Returns/Refunds
        "MDCL_CD": "01"  # Medium Category: General Policy
    },
    {
        "faq_id": "FAQ002_KO",
        "CUST_QUEST": "타이어 장착 후 반품이 가능한가요?",
        "PC_ANS_CONT": "차량에 타이어를 장착하고 주행한 이후에는 확인 가능한 제조상 결함이 없는 한 반품이 불가합니다. 장착 전에 타이어의 상태를 확인해 주시기 바랍니다.",
        "LRCL_CD": "02",
        "MDCL_CD": "01" 
    },

    # ---------------------------------------------------------
    # Category: Product Info (03)
    # ---------------------------------------------------------
    {
        "faq_id": "FAQ003_EN",
        "CUST_QUEST": "What is the standard warranty on Hankook tires?",
        "PC_ANS_CONT": "Hankook tires come with a standard 6-year warranty against manufacturing defects from the date of manufacture. Treadwear warranties vary by specific tire model. Please check the product description for specific mileage warranties.",
        "LRCL_CD": "03", # Large Category: Product Info
        "MDCL_CD": "02"  # Medium Category: Warranty
    },
    {
        "faq_id": "FAQ003_KO",
        "CUST_QUEST": "한국타이어의 기본 보증 기간은 어떻게 되나요?",
        "PC_ANS_CONT": "한국타이어는 제조일로부터 제조상 결함에 대해 기본 6년 보증을 제공합니다. 마모 보증은 타이어 모델에 따라 다릅니다. 특정 마일리지 보증은 제품 상세 설명을 참조해 주시기 바랍니다.",
        "LRCL_CD": "03", 
        "MDCL_CD": "02"  
    },

    # ---------------------------------------------------------
    # Category: Store Services (04)
    # ---------------------------------------------------------
    {
        "faq_id": "FAQ004_EN",
        "CUST_QUEST": "Do you offer free alignment checks?",
        "PC_ANS_CONT": "Yes, we offer a free visual alignment check for all customers. However, if a full laser alignment adjustment is required, standard labor rates will apply.",
        "LRCL_CD": "04", # Large Category: Store Services
        "MDCL_CD": "01"  # Medium Category: Maintenance
    },
    {
        "faq_id": "FAQ004_KO",
        "CUST_QUEST": "무료 휠 얼라인먼트 점검을 제공하나요?",
        "PC_ANS_CONT": "네, 모든 방문 고객님께 무료 육안 얼라인먼트 점검을 제공합니다. 단, 정밀한 레이저 얼라인먼트 조정 작업이 필요한 경우 표준 공임비가 청구됩니다.",
        "LRCL_CD": "04", 
        "MDCL_CD": "01"  
    }
]


@tool
def search_faq(query: str) -> list[dict]:
    """
    Mock FAQ AF: GET /api/faq/search
    Supports Korean query by mapping keywords.
    """

    return MOCK_FAQ_DB
