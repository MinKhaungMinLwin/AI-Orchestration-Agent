from enum import Enum


class SupportedLanguage(str, Enum):
    EN = "en"
    KO = "ko"

class QuestionCategory(str, Enum):
    HOLISTIC_SHOPPING = "holistic_shopping"
    PRODUCT_SEARCH = "product_search"
    PRODUCT_COMPATIBILITY = "product_compatibility"
    PRICING = "pricing"
    INVENTORY = "inventory"
    STORE_LOCATOR = "store_locator"
    PRODUCT_RECOMMENDATION = "product_recommendation"
    ORDER_BOOKING = "order_booking"
    FAQ_SUPPORT = "faq_support"
