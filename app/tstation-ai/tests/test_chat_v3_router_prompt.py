import runpy
from pathlib import Path


_ROUTER = runpy.run_path(Path("services/tstation/chat_v3/prompts/router.py"))
ROUTER_PROMPT = _ROUTER["ROUTER_PROMPT"]


def test_router_routes_bare_info_to_the_domain_that_can_use_it():
    # A message with no request verb but enough info to call a tool's required
    # args (e.g. car_no + owner_nm) must not be classified as LEADING — the
    # info itself is the intent.
    assert "요청 문구가 없어도" in ROUTER_PROMPT
    assert "LEADING(잡담)으로 분류해 정보를 흘려보내지" in ROUTER_PROMPT
    assert "09조8765 홍길동" in ROUTER_PROMPT
