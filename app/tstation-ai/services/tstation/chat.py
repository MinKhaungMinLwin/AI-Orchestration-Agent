import json
import logging


from services.tstation.common.tstation_be_client import set_tstation_be_token
from config.env import settings
from fastapi.responses import StreamingResponse
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.agents.router import AgentDomain, leading_agent
from common.jwt_utils import get_user_info_from_token

logger = logging.getLogger(__name__)


class TStationChatService(object):
    __instance = None

    @staticmethod
    def _build_messages_with_user_info(request: TStationChatRequest) -> list[dict]:
        """
        Build messages with user info injected from JWT token.
        """
        messages = list(request.messages)

        # Decode JWT to get user info
        user_info = None
        if request.access_token:
            user_info = get_user_info_from_token(request.access_token)

        if user_info:
            # Create a system message with user info
            user_info_str = ", ".join([f"{k}: {v}" for k, v in user_info.items()])
            user_context_msg = {
                "role": "system",
                "content": f"[User Context] {user_info_str}"
            }
            # Insert user context as first message (after any existing system messages)
            messages = [user_context_msg] + messages
            logger.info(f"[CHAT] User info injected: {user_info_str}")

        return messages

    @staticmethod
    def chat(request: TStationChatRequest):
        """

        T-Station AI Chat

        Workflow
        1. Classify the request
        2. Delegate to the appropriate agent

        """

        logger.debug(f"Received /tstation/chat request: {request}")

        # Set auth key for tstation-be API calls (per-request)
        logger.info(f"[CHAT] Setting access_token: {request.access_token[:50] if request.access_token else None}...")
        set_tstation_be_token(request.access_token)

        # Build messages with user info from JWT
        messages = TStationChatService._build_messages_with_user_info(request)
        logger.debug(f"[CHAT] Messages sent to agent: {json.dumps(messages, ensure_ascii=False, indent=2)}")

        # 1. Classify the request
        domain = TStationChatService.classify_domain_request(request)
        agent = AgentDomain(domain=domain, reason="", confidence=0.0).get_agent()

        # 2. Delegate to the appropriate agent
        # STREAM MODE
        if request.stream:
            return StreamingResponse(
                TStationChatService._stream_response(
                    agent,
                    messages
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
            content = leading_agent.invoke(messages)
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
        from langchain_core.messages import SystemMessage

        llm = ChatLiteLLM(
            api_base=settings.AI_GATEWAY_BASE_URL,
            api_key=settings.AI_GATEWAY_API_KEY,
            model="gpt-5.4",
        )

        structured_model = llm.with_structured_output(
            AgentDomain,
            strict=True,
        )

        try:
            # Inject classification prompt as system message
            system_msg = SystemMessage(content=AgentDomain.prompt_router())
            all_messages = [system_msg] + list(request.messages)

            result: AgentDomain = structured_model.invoke(all_messages)
            logger.info(f"[DOMAIN] Domain classification result: {result}")
            return result.domain

        except Exception as e:
            logger.exception(f"[DOMAIN] Domain classification failed: {e}")
            return AgentDomain.Domain.LEADING


    @staticmethod
    def _stream_response(
            agent,
            messages: list[dict]
    ):

        for event in agent.stream(messages):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
