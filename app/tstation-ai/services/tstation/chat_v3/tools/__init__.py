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


def tools_for_domains(domains: list[str]) -> list:
    """Union of the domains' tools, deduped by tool name (V2 chained agents
    per domain; V3 gives one LLM every tool the turn needs instead)."""
    seen: set[str] = set()
    union = []
    for domain in domains:
        for tool in tools_for_domain(domain):
            if tool.name not in seen:
                seen.add(tool.name)
                union.append(tool)
    return union
