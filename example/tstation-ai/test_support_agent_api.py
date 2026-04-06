"""
Raw API Test - Support Agent Chat with RAG Integration

This script tests the Support Agent API endpoint directly without going through multi-agent orchestration.

It demonstrates:
1. How the Support Agent calls search_faq_rag_tool internally
2. How RAG retrieves relevant FAQ documents
3. How LLM synthesizes answer from retrieved FAQs
4. End-to-end flow with streaming

Usage:
    python example/tstation-ai/test_support_agent_api.py
"""

import json
import sys
import os
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "app" / "tstation-ai"))

# Load .env
from dotenv import load_dotenv
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_faq_data():
    """Prepare FAQ data in Qdrant."""
    from services.tstation.rag import (
        get_qdrant_service,
        get_embedding_service,
        DocumentProcessor,
    )
    from config.env import settings

    logger.info("=" * 80)
    logger.info("SETUP: Preparing FAQ Data in Qdrant")
    logger.info("=" * 80 + "\n")

    # Load test data
    data_path = Path(__file__).parent / "faq_test_data.json"
    with open(data_path, "r", encoding="utf-8") as f:
        documents = json.load(f)

    # Initialize services
    qdrant_svc = get_qdrant_service(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
    )

    openai_api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY

    embedding_svc = get_embedding_service(
        model=settings.EMBEDDING_MODEL,
        provider=settings.EMBEDDING_PROVIDER,
        api_key=openai_api_key,
    )

    # Create collection
    qdrant_svc.create_collection(
        collection_name=settings.QDRANT_COLLECTION_FAQ,
        vector_size=embedding_svc.get_embedding_dimension(),
    )

    # Process and index documents
    prepared_docs = DocumentProcessor.prepare_for_indexing(
        documents=documents,
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
    )

    contents = [doc["content"] for doc in prepared_docs]
    embeddings = embedding_svc.embed_texts(contents)

    result = qdrant_svc.upsert_documents(
        collection_name=settings.QDRANT_COLLECTION_FAQ,
        documents=prepared_docs,
        vectors=embeddings,
    )

    logger.info(f"✓ Indexed {result['upserted_count']} FAQ documents\n")


def create_agent():
    """Create Support Agent."""
    from langchain_litellm import ChatLiteLLM
    from services.tstation.agents.e_support_agent.agent import SupportSubAgent
    from config.env import settings

    logger.info("=" * 80)
    logger.info("AGENT: Creating Support Agent with RAG")
    logger.info("=" * 80 + "\n")

    llm = ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL}",
        temperature=0.7,
    )

    agent = SupportSubAgent(model=llm)
    logger.info("✓ Support Agent created\n")

    return agent


def stream_agent_response(agent, user_query: str):
    """Stream agent response and display all events."""
    logger.info("=" * 80)
    logger.info(f"USER QUERY: {user_query}")
    logger.info("=" * 80 + "\n")

    messages = [{"role": "user", "content": user_query}]

    # Tracking variables
    tool_calls = []
    faq_results = []
    full_response = ""

    logger.info("[AGENT STREAMING]\n")

    # Stream events from agent
    for event in agent.stream(messages):
        event_type = event.get("type")

        if event_type == "agent_flow":
            agent_name = event.get("agent", "Unknown")
            status = event.get("status", "unknown")
            logger.info(f"📍 {agent_name}: {status}\n")

        elif event_type == "token":
            # LLM token output
            content = event.get("content", "")
            print(content, end="", flush=True)
            full_response += content

        elif event_type == "tool":
            # Tool execution event
            tool_name = event.get("tool", "unknown")
            tool_input = event.get("input", {})
            tool_output = event.get("output", "")

            logger.info(f"\n\n🔧 TOOL INVOKED: {tool_name}")
            logger.info(f"   Query: {tool_input.get('query', 'N/A')}\n")

            # Parse and display results
            try:
                if isinstance(tool_output, str):
                    output_data = json.loads(tool_output)
                else:
                    output_data = tool_output

                if output_data.get("status") == "success":
                    results = output_data.get("data", [])
                    logger.info(f"   📌 Found {len(results)} relevant FAQs:\n")

                    for idx, result in enumerate(results[:5], 1):
                        content = result.get("content", "")
                        score = result.get("score", 0)
                        logger.info(f"      {idx}. [Relevance: {score:.1%}] {content[:80]}...\n")

                    faq_results = results
                    tool_calls.append({
                        "name": tool_name,
                        "query": tool_input.get("query"),
                        "results_count": len(results),
                    })
                else:
                    logger.info(f"   ⚠️ Tool error: {output_data.get('message', 'Unknown error')}\n")

            except json.JSONDecodeError:
                logger.info(f"   Output: {tool_output[:200]}\n")

        elif event_type == "message":
            pass

    print("\n")

    logger.info("=" * 80)
    logger.info("ANALYSIS")
    logger.info("=" * 80)
    logger.info(f"Response Length: {len(full_response)} characters")
    logger.info(f"Tool Calls Made: {len(tool_calls)}")

    for tc in tool_calls:
        logger.info(f"  • {tc['name']}")
        logger.info(f"    Query: '{tc['query']}'")
        logger.info(f"    Results: {tc['results_count']} FAQs found")

    logger.info(f"Final Answer Length: {len(full_response)} characters\n")

    return {
        "query": user_query,
        "response": full_response,
        "tool_calls": tool_calls,
        "faq_results_count": len(faq_results),
    }


def test_conversation():
    """Test a full FAQ conversation flow."""
    test_cases = [
        "How long does tire installation take?",
        "Can I get a refund if I'm not satisfied?",
        "What warranty do you offer?",
        "Do you have winter tires available?",
        "I need roadside assistance, what should I do?",
    ]

    logger.info("\n")
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║" + " " * 12 + "SUPPORT AGENT LIVE TEST WITH RAG INTEGRATION" + " " * 22 + "║")
    logger.info("╚" + "=" * 78 + "╝")
    logger.info("\n")

    results = []

    for query in test_cases:
        result = stream_agent_response(agent, query)
        results.append(result)

        logger.info("\n" + "—" * 80 + "\n")

    return results


if __name__ == "__main__":
    try:
        # Setup
        setup_faq_data()

        # Create agent
        agent = create_agent()

        # Run test conversation
        results = test_conversation()

        # Summary
        logger.info("=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total Queries: {len(results)}")
        logger.info(f"Total Tool Calls: {sum(len(r['tool_calls']) for r in results)}")
        logger.info(f"Avg Response Length: {sum(len(r['response']) for r in results) // len(results)} chars\n")

        logger.info("✓ ALL TESTS COMPLETED SUCCESSFULLY")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        sys.exit(1)
