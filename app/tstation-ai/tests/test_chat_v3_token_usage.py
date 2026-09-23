from __future__ import annotations

from types import SimpleNamespace

from services.tstation.chat_v3.token_usage import TurnTokenUsage


def _fake_llm_response(usage: dict | None = None, llm_output_usage: dict | None = None):
    message = SimpleNamespace(usage_metadata=usage)
    generation = SimpleNamespace(message=message)
    return SimpleNamespace(
        generations=[[generation]],
        llm_output={"token_usage": llm_output_usage} if llm_output_usage else None,
    )


def test_add_sums_total_tokens_field():
    tracker = TurnTokenUsage()
    tracker.add({"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
    assert tracker.total_tokens == 150


def test_add_falls_back_to_input_plus_output_when_total_missing():
    tracker = TurnTokenUsage()
    tracker.add({"input_tokens": 100, "output_tokens": 50})
    assert tracker.total_tokens == 150


def test_add_falls_back_to_openai_style_prompt_completion_fields():
    tracker = TurnTokenUsage()
    tracker.add({"prompt_tokens": 200, "completion_tokens": 30})
    assert tracker.total_tokens == 230


def test_add_none_or_empty_is_a_noop():
    tracker = TurnTokenUsage()
    tracker.add(None)
    tracker.add({})
    assert tracker.total_tokens == 0


def test_add_accumulates_across_multiple_calls():
    tracker = TurnTokenUsage()
    tracker.add({"total_tokens": 100})
    tracker.add({"total_tokens": 250})
    assert tracker.total_tokens == 350


def test_callback_reads_usage_metadata_from_message():
    tracker = TurnTokenUsage()
    handler = tracker.callback()
    response = _fake_llm_response(usage={"total_tokens": 420})
    handler.on_llm_end(response)
    assert tracker.total_tokens == 420


def test_callback_falls_back_to_llm_output_token_usage():
    tracker = TurnTokenUsage()
    handler = tracker.callback()
    response = _fake_llm_response(usage=None, llm_output_usage={"total_tokens": 88})
    handler.on_llm_end(response)
    assert tracker.total_tokens == 88


def test_callback_accumulates_across_multiple_rounds_sharing_one_tracker():
    # Mirrors the real usage: one tracker's callback attached to every LLM call
    # in a turn (router, each tool-loop round, QC, ...) via the same trace_config.
    tracker = TurnTokenUsage()
    handler = tracker.callback()
    handler.on_llm_end(_fake_llm_response(usage={"total_tokens": 300}))
    handler.on_llm_end(_fake_llm_response(usage={"total_tokens": 150}))
    handler.on_llm_end(_fake_llm_response(usage={"total_tokens": 75}))
    assert tracker.total_tokens == 525


def test_callback_ignores_malformed_response_without_raising():
    tracker = TurnTokenUsage()
    handler = tracker.callback()
    handler.on_llm_end(SimpleNamespace(generations=[], llm_output=None))
    assert tracker.total_tokens == 0
