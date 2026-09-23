"""Support tools — FAQ (RAG), warranty, escalation.

Re-exports from agents/e_support_agent/tools.py.
"""

from services.tstation.agents.e_support_agent.tools import (
    check_coupon_stacking_tool,
    get_card_installments_tool,
    get_maintenance_dday_tool,
    get_my_relief_services_tool,
    get_my_warranties_tool,
    get_product_warranties_tool,
    get_static_faq_policy_tool,
    search_faq_hybrid_tool,
    transfer_to_qna_tool,
)

SUPPORT_TOOLS = [
    get_static_faq_policy_tool,
    search_faq_hybrid_tool,
    get_product_warranties_tool,
    get_my_relief_services_tool,
    get_my_warranties_tool,
    get_maintenance_dday_tool,
    get_card_installments_tool,
    check_coupon_stacking_tool,
    transfer_to_qna_tool,
]
