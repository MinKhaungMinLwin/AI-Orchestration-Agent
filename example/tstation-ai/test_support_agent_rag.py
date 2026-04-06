"""
Support Agent + RAG Integration Test

This script tests the Support Agent with RAG-powered FAQ search.

Flow:
1. Load and index FAQ test documents into Qdrant
2. Create Support Agent with LangChain LLM
3. Send user queries to agent
4. Stream agent responses with tool calls
5. Observe how agent uses search_faq_rag_tool

Usage:
    python example/tstation-ai/test_support_agent_rag.py
"""

import json
import sys
import os
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "app" / "tstation-ai"))

# Load .env before importing
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


def load_and_index_faq():
    """Load test FAQ documents and index into Qdrant."""
    from services.tstation.rag import (
        get_qdrant_service,
        get_embedding_service,
        DocumentProcessor,
    )
    from config.env import settings

    logger.info("=" * 80)
    logger.info("STEP 1: Loading and Indexing FAQ Documents")
    logger.info("=" * 80)

    # Load test data
    data_path = Path(__file__).parent / "faq_test_data.json"
    with open(data_path, "r", encoding="utf-8") as f:
        documents = json.load(f)

    logger.info(f"Loaded {len(documents)} FAQ documents")

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
    logger.info(f"Creating Qdrant collection: {settings.QDRANT_COLLECTION_FAQ}")
    qdrant_svc.create_collection(
        collection_name=settings.QDRANT_COLLECTION_FAQ,
        vector_size=embedding_svc.get_embedding_dimension(),
    )

    # Process documents
    logger.info("Processing documents (chunking)...")
    prepared_docs = DocumentProcessor.prepare_for_indexing(
        documents=documents,
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
    )

    logger.info(f"Created {len(prepared_docs)} chunks")

    # Generate embeddings
    logger.info("Generating embeddings...")
    contents = [doc["content"] for doc in prepared_docs]
    embeddings = embedding_svc.embed_texts(contents)

    # Index documents
    logger.info("Indexing into Qdrant...")
    result = qdrant_svc.upsert_documents(
        collection_name=settings.QDRANT_COLLECTION_FAQ,
        documents=prepared_docs,
        vectors=embeddings,
    )

    logger.info(f"✓ Indexed {result['upserted_count']} documents")
    stats = qdrant_svc.get_collection_stats(settings.QDRANT_COLLECTION_FAQ)
    logger.info(f"Collection: {stats}\n")


def create_support_agent():
    """Create Support Agent with LangChain."""
    from langchain_litellm import ChatLiteLLM
    from services.tstation.agents.e_support_agent.agent import SupportSubAgent
    from config.env import settings

    logger.info("=" * 80)
    logger.info("STEP 2: Creating Support Agent")
    logger.info("=" * 80)

    # Create LLM
    llm = ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL}",
        temperature=0.7,
    )

    logger.info(f"LLM: {settings.AI_MODEL}")
    logger.info(f"Gateway: {settings.AI_GATEWAY_BASE_URL}\n")

    # Create agent
    agent = SupportSubAgent(model=llm)
    logger.info("✓ Support Agent created\n")

    return agent


def test_agent_query(agent, query: str):
    """Test agent with a user query."""
    logger.info("=" * 80)
    logger.info(f"QUERY: {query}")
    logger.info("=" * 80)

    # Build messages
    messages = [
        {"role": "user", "content": query}
    ]

    logger.info("\n[Agent Streaming Output]\n")

    # Stream agent response
    full_response = ""
    tool_calls = []

    for event in agent.stream(messages):
        event_type = event.get("type")

        if event_type == "agent_flow":
            agent_name = event.get("agent", "Unknown")
            status = event.get("status", "unknown")
            logger.info(f"📍 {agent_name}: {status}")

        elif event_type == "token":
            content = event.get("content", "")
            print(content, end="", flush=True)
            full_response += content

        elif event_type == "tool":
            tool_name = event.get("tool", "unknown")
            tool_input = event.get("input", {})
            tool_output = event.get("output", "")

            logger.info(f"\n\n🔧 Tool: {tool_name}")
            logger.info(f"   Input: {json.dumps(tool_input, indent=6)}")

            # Parse tool output
            try:
                if isinstance(tool_output, str):
                    output_data = json.loads(tool_output)
                else:
                    output_data = tool_output

                if isinstance(output_data, dict) and "data" in output_data:
                    results = output_data["data"]
                    if isinstance(results, list):
                        logger.info(f"   Results ({len(results)} FAQs found):")
                        for idx, result in enumerate(results[:3], 1):
                            content = result.get("content", "")[:100]
                            score = result.get("score", 0)
                            logger.info(
                                f"     {idx}. [Score: {score:.3f}] {content}..."
                            )
                    tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                        "output_count": len(results) if isinstance(results, list) else 0,
                    })
            except json.JSONDecodeError:
                logger.info(f"   Output: {tool_output[:200]}")

        elif event_type == "message":
            # Intermediate message
            pass

    print("\n")

    logger.info("=" * 80)
    logger.info("AGENT RESPONSE SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Response Length: {len(full_response)} chars")
    logger.info(f"Tool Calls: {len(tool_calls)}")
    for tc in tool_calls:
        logger.info(f"  - {tc['name']} ({tc['output_count']} results)")
    logger.info("")


def test_multiple_queries(agent):
    """Test agent with multiple queries."""
    test_queries = [
        "How long does tire installation take?",
        "Can I get a refund?",
        "What is your warranty policy?",
        "Do you have winter tires?",
        "How do I contact roadside assistance?",
    ]

    for query in test_queries:
        test_agent_query(agent, query)
        logger.info("\n")


def main():
    """Main test flow."""
    logger.info("\n")
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║" + " " * 15 + "SUPPORT AGENT + RAG INTEGRATION TEST" + " " * 27 + "║")
    logger.info("╚" + "=" * 78 + "╝")
    logger.info("\n")

    try:
        # Step 1: Load and index FAQ documents
        load_and_index_faq()

        # Step 2: Create Support Agent
        agent = create_support_agent()

        # Step 3: Test with queries
        test_multiple_queries(agent)

        logger.info("=" * 80)
        logger.info("✓ ALL TESTS COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
