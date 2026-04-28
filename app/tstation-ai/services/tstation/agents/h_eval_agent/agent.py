import logging

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from services.tstation.agents.h_eval_agent.rubrics import FAITHFULNESS_PROMPT

logger = logging.getLogger(__name__)


class GEvalScore(BaseModel):
    reasoning: str = Field(description="Step-by-step analysis following the evaluation steps in the rubric.")
    score: int = Field(description="Final score on the 1-5 scale defined in the rubric.", ge=1, le=5)


def _build_faithfulness_chain(llm):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", FAITHFULNESS_PROMPT),
            (
                "user",
                "User Query:\n{user_query}\n\nSOURCE DATA (tool outputs):\n{source_data}\n\nResponse:\n{response}",
            ),
        ]
    )
    structured = llm.with_structured_output(GEvalScore)
    return prompt | structured


def score_faithfulness(
    llm,
    *,
    user_query: str,
    response: str,
    source_data: str,
) -> GEvalScore:
    chain = _build_faithfulness_chain(llm)
    return chain.invoke(
        {
            "user_query": user_query,
            "response": response,
            "source_data": source_data or "(no tool outputs collected for this turn)",
        }
    )
