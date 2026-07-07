"""Tool registry: routed domain → tools bound to the LLM.

Imports are lazy — agent tool modules pull in the BE API client, so we
only pay that cost when a domain actually needs tools.
"""


def tools_for_domain(domain: str) -> list:
    if domain == "DISCOVERY":
        from services.tstation.chat_v3.tools.discovery import DISCOVERY_TOOLS

        return DISCOVERY_TOOLS
    if domain == "TRANSACTION":
        from services.tstation.chat_v3.tools.transaction import TRANSACTION_TOOLS

        return TRANSACTION_TOOLS
    if domain == "SUPPORT":
        from services.tstation.chat_v3.tools.support import SUPPORT_TOOLS

        return SUPPORT_TOOLS
    return []  # LEADING — pure conversation, no tools
