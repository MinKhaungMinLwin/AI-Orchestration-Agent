"""Common response decision contracts for deterministic policy modules.

Integration note:
    Domain policies should return ``ToolPlan`` and ``ResponseDecision`` objects.
    Later integration points in chat/base-agent/template-mapper can consume these
    objects without re-deriving policy from assistant copy or FE labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping


class ResponseShape(str, Enum):
    """Stable response shape names used before FE template rendering."""

    TEXT = "text"
    CLARIFY = "clarify"
    SUMMARY = "summary"
    LIST = "list"
    CARD = "card"
    DATE_PICK = "date_pick"
    LOCATION = "location"
    ACTION_CONFIRM = "action_confirm"
    NO_RESULT = "no_result"


class TemplateName(str, Enum):
    """FE template names that policy code may choose deterministically."""

    TEXT = "text"
    QUICK_REPLY = "quickReply"
    PRODUCT = "product"
    LOCATION = "location"
    DATE_PICK = "datepick"
    LIST_CAR = "listCar"
    VOUCHER = "voucher"
    PRE_ORDER = "preOrder"
    ORDER_COMPLETE = "orderComplete"
    QNA_COMPLETE = "qnaComplete"
    NONE = "none"


@dataclass(frozen=True)
class ToolPlan:
    """Allowed tool contract produced by policy before agent execution."""

    allowed_tools: tuple[str, ...] = ()
    preferred_tool: str | None = None
    tool_args_patch: Mapping[str, Any] = field(default_factory=dict)
    forbidden_tools: tuple[str, ...] = ()
    required_slots: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def allows(self, tool_name: str) -> bool:
        if tool_name in self.forbidden_tools:
            return False
        return not self.allowed_tools or tool_name in self.allowed_tools

    def with_args_patch(self, **patch: Any) -> "ToolPlan":
        return replace(self, tool_args_patch={**dict(self.tool_args_patch), **patch})

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_tools": list(self.allowed_tools),
            "preferred_tool": self.preferred_tool,
            "tool_args_patch": dict(self.tool_args_patch),
            "forbidden_tools": list(self.forbidden_tools),
            "required_slots": list(self.required_slots),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ResponseDecision:
    """Deterministic response contract consumed by mapper or LLM copywriting."""

    response_shape: ResponseShape
    template: TemplateName = TemplateName.QUICK_REPLY
    required_slots: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    assistant_guidance: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def clarify(
        cls,
        *required_slots: str,
        assistant_guidance: str = "",
        forbidden_behaviors: tuple[str, ...] = (),
    ) -> "ResponseDecision":
        return cls(
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=tuple(required_slots),
            forbidden_behaviors=forbidden_behaviors,
            assistant_guidance=assistant_guidance,
        )

    def forbids(self, behavior: str) -> bool:
        return behavior in self.forbidden_behaviors

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_shape": self.response_shape.value,
            "template": self.template.value,
            "required_slots": list(self.required_slots),
            "forbidden_behaviors": list(self.forbidden_behaviors),
            "assistant_guidance": self.assistant_guidance,
            "metadata": dict(self.metadata),
        }

