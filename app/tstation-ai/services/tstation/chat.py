import json
import logging
import re
import time
import uuid
from pathlib import Path
from textwrap import dedent

import pandas as pd
import requests
from langchain_openai import ChatOpenAI

from celery_app import redis as redis_client
from common.curr_time import get_current_time
from common.detect_language import SupportedLanguage, detect_language
from config.env import settings
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.agents.router import AgentDomain, leading_agent, discovery_subagent, LLM

logger = logging.getLogger(__name__)


class TStationChatService(object):
    __instance = None

    @staticmethod
    def chat(request: TStationChatRequest):
        """

        T-Station AI Chat

        Workflow
        1. Classify the request
        2. Delegate to the appropriate agent

        """

        logger.debug(f"Received /tstation/chat request: {request}")

        # 1. Classify the request
        domain = TStationChatService.classify_domain_request(request)
        agent = AgentDomain(domain=domain).get_agent()

        # 2. Delegate to the appropriate agent
        # STREAM MODE
        if request.stream:
            return StreamingResponse(
                TStationChatService._stream_response(
                    agent,
                    request
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # NON STREAM MODE
        try:
            content = leading_agent.invoke(request.messages)
            return TStationChatResponse(
                content=content
            )

        except ValueError as e:
            logger.warning(f"User Error: {e}")
            raise ValueError(e)
        except Exception as e:
            logger.exception(f"Server Error: {e}")
            raise Exception("Internal Server Error")


    @staticmethod
    def classify_domain_request(request: TStationChatRequest) -> AgentDomain.Domain:

        from langchain_litellm import ChatLiteLLM

        llm = ChatLiteLLM(
            model="bedrock/arn:aws:bedrock:ap-northeast-2:763865062538:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
            # model = "bedrock/ap-northeast-1/arn:aws:bedrock:ap-northeast-1:763865062538:inference-profile/minimax.minimax-m2-1",
            temperature=0.3,
            streaming=True,
        )

        structured_model = llm.with_structured_output(
            AgentDomain,
            strict=True,
        )

        try:
            result: AgentDomain = structured_model.invoke(request.messages)
            logger.debug(f"Domain classification result: {result}")
            return result.domain

        except Exception as e:
            logger.exception(f"Domain classification failed: {e}")
            return AgentDomain.Domain.LEADING


    @staticmethod
    def _stream_response(
            agent,
            request: TStationChatRequest
    ):

        for event in agent.stream(request.messages):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
