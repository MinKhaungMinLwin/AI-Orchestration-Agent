from langchain.tools import tool

# ==========================================
# MOCK FAQ DATABASE – T-STATION (CS_CUST_INQ_MGMT_INFO)
# ==========================================

MOCK_FAQ_DB = [
    {
        "faq_id": "FAQ001",
        "CUST_QUEST": "How do I cancel or change my tire installation appointment?",
        "PC_ANS_CONT": "You can cancel or change your appointment by navigating to 'My Page' > 'Order/Reservation History'. Changes must be made at least 24 hours prior to your scheduled time. If it is within 24 hours, please contact the specific T-Station store directly.",
        "LRCL_CD": "01", # Large Category: Reservation
        "MDCL_CD": "01"  # Medium Category: Change/Cancel
    },
    {
        "faq_id": "FAQ002",
        "CUST_QUEST": "Can I return tires after they have been installed?",
        "PC_ANS_CONT": "Once tires have been mounted on your vehicle and driven, they cannot be returned unless there is a verifiable manufacturing defect. Please inspect your tires before installation.",
        "LRCL_CD": "02", # Large Category: Returns/Refunds
        "MDCL_CD": "01"  # Medium Category: General Policy
    },
    {
        "faq_id": "FAQ003",
        "CUST_QUEST": "What is the standard warranty on Hankook tires?",
        "PC_ANS_CONT": "Hankook tires come with a standard 6-year warranty against manufacturing defects from the date of manufacture. Treadwear warranties vary by specific tire model. Please check the product description for specific mileage warranties.",
        "LRCL_CD": "03", # Large Category: Product Info
        "MDCL_CD": "02"  # Medium Category: Warranty
    },
    {
        "faq_id": "FAQ004",
        "CUST_QUEST": "Do you offer free alignment checks?",
        "PC_ANS_CONT": "Yes, we offer a free visual alignment check for all customers. However, if a full laser alignment adjustment is required, standard labor rates will apply.",
        "LRCL_CD": "04", # Large Category: Store Services
        "MDCL_CD": "01"  # Medium Category: Maintenance
    }
]

@tool
def search_faq(query: str) -> dict:
    """
    Mock FAQ AF: GET /api/faq/search
    Searches the FAQ database based on a keyword.
    """
    query_lower = query.lower()
    results = []

    for faq in MOCK_FAQ_DB:
        # Simple mock search matching keywords in question or answer
        if query_lower in faq["CUST_QUEST"].lower() or query_lower in faq["PC_ANS_CONT"].lower():
            results.append({
                "CUST_QUEST": faq["CUST_QUEST"],
                "PC_ANS_CONT": faq["PC_ANS_CONT"],
                "LRCL_CD": faq["LRCL_CD"],
                "MDCL_CD": faq["MDCL_CD"]
            })

    return {
        "query": query,
        "total_found": len(results),
        "results": results
    }