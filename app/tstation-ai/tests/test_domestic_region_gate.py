from services.tstation.policies.domestic_region_gate import (
    DomesticRegionGateDecision,
    decide_domestic_search_area,
    deterministic_domestic_region_gate_decision,
)


class _FakeGateModel:
    def __init__(self, decision: DomesticRegionGateDecision):
        self.decision = decision
        self.prompts: list[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        return self.decision


def test_domestic_region_gate_blocks_known_foreign_region_without_llm() -> None:
    decision = deterministic_domestic_region_gate_decision("평양")

    assert decision is not None
    assert decision.is_domestic_search_area is False
    assert decision.kind == "foreign_region"


def test_domestic_region_gate_allows_domestic_landmark_without_llm() -> None:
    decision = deterministic_domestic_region_gate_decision("강남구청")

    assert decision is not None
    assert decision.is_domestic_search_area is True
    assert decision.kind == "domestic_landmark"


def test_domestic_region_gate_uses_llm_for_ambiguous_domestic_area() -> None:
    model = _FakeGateModel(
        DomesticRegionGateDecision(
            is_domestic_search_area=True,
            kind="domestic_region",
            reason="광교 is a domestic area name.",
        )
    )

    decision = decide_domestic_search_area("광교", model=model)

    assert decision.is_domestic_search_area is True
    assert decision.kind == "domestic_region"
    assert model.prompts
    assert "한국 내 지역명" in model.prompts[0] or "Korea domestic" in model.prompts[0]
