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
from common.openai import MetadataTracing, OpenAIWithTracing, TracingRequest
from config.env import settings
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.agents.main_leading_agent import LeadingAgent, discovery_subagent

logger = logging.getLogger(__name__)


class TStationChatService(object):
    __instance = None

    @staticmethod
    def chat(request: TStationChatRequest):

        logger.debug(f"Received /tstation/chat request: {request}")

        # leading_agent = LeadingAgent()
        leading_agent = discovery_subagent

        # STREAM MODE
        if request.stream:
            return StreamingResponse(
                TStationChatService._stream_response(
                    leading_agent,
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
    def _stream_response(
            leading_agent: LeadingAgent,
            request: TStationChatRequest
    ):

        for event in leading_agent.stream(request.messages):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
