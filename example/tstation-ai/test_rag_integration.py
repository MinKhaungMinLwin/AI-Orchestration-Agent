"""
RAG Integration Test Script for FAQ System

This script demonstrates how to:
1. Load test FAQ data
2. Generate embeddings
3. Index documents into Qdrant
4. Perform semantic search queries
5. Integrate with Support Agent

Usage:
    python example/tstation-ai/test_rag_integration.py
"""

import json
import sys
import os
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "app" / "tstation-ai"))

# Load .env before importing anything
from dotenv import load_dotenv
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    print(f"Warning: .env file not found at {env_file}")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_test_data():
    """Load FAQ test data from JSON file."""
    data_path = Path(__file__).parent / "faq_test_data.json"
    
    with open(data_path, "r", encoding="utf-8") as f:
        documents = json.load(f)
    
    logger.info(f"Loaded {len(documents)} FAQ documents from {data_path}")
    return documents


def setup_rag():
    """Initialize RAG services and create Qdrant collection."""
    from services.tstation.rag import (
        get_qdrant_service,
        get_embedding_service,
        DocumentProcessor,
        ChunkingService,
    )
    from config.env import settings

    # Initialize services
    logger.info("Initializing RAG services...")
    
    qdrant_svc = get_qdrant_service(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
    )
    
    # Get API key from settings or environment
    openai_api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
    
    embedding_svc = get_embedding_service(
        model=settings.EMBEDDING_MODEL,
        provider=settings.EMBEDDING_PROVIDER,
        api_key=openai_api_key,
    )
    
    # Check Qdrant health
    if not qdrant_svc.health_check():
        raise RuntimeError(
            f"Qdrant server is not accessible at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}. "
            "Please start Qdrant first with: docker-compose -f docker_local/docker-compose-llm.yml up qdrant"
        )
    
    logger.info(f"✓ Qdrant connected: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    
    # Check embedding service
    if not embedding_svc.health_check():
        raise RuntimeError(
            f"Embedding service ({settings.EMBEDDING_PROVIDER}) is not accessible. "
            f"Please set OPENAI_API_KEY in .env or environment"
        )
    
    logger.info(f"✓ Embedding service ready: {settings.EMBEDDING_MODEL}")
    
    return qdrant_svc, embedding_svc


def index_documents(documents):
    """Index test documents into Qdrant."""
    from services.tstation.rag import (
        get_qdrant_service,
        get_embedding_service,
        DocumentProcessor,
    )
    from config.env import settings

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

    logger.info("Step 1: Creating Qdrant collection...")
    qdrant_svc.create_collection(
        collection_name=settings.QDRANT_COLLECTION_FAQ,
        vector_size=embedding_svc.get_embedding_dimension(),
    )

    logger.info("Step 2: Processing documents...")
    prepared_docs = DocumentProcessor.prepare_for_indexing(
        documents=documents,
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
    )
    
    logger.info(f"  → {len(prepared_docs)} chunks created from {len(documents)} documents")

    logger.info("Step 3: Generating embeddings...")
    contents = [doc["content"] for doc in prepared_docs]
    embeddings = embedding_svc.embed_texts(contents)
    logger.info(f"  → Generated {len(embeddings)} embeddings")

    logger.info("Step 4: Indexing into Qdrant...")
    result = qdrant_svc.upsert_documents(
        collection_name=settings.QDRANT_COLLECTION_FAQ,
        documents=prepared_docs,
        vectors=embeddings,
    )

    logger.info(f"✓ Indexed: {result['upserted_count']} documents")
    
    # Print collection stats
    stats = qdrant_svc.get_collection_stats(settings.QDRANT_COLLECTION_FAQ)
    logger.info(f"  Collection stats: {stats}")


def search_faq(query: str, top_k: int = 5, score_threshold: float = 0.7):
    """Perform semantic search on FAQ documents."""
    from services.tstation.rag import (
        get_qdrant_service,
        get_embedding_service,
    )
    from config.env import settings

    logger.info(f"\nSearching for: '{query}'")
    logger.info(f"  top_k={top_k}, score_threshold={score_threshold}")

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

    # Generate query embedding
    query_embedding = embedding_svc.embed_text(query)

    # Search
    results = qdrant_svc.search(
        collection_name=settings.QDRANT_COLLECTION_FAQ,
        query_vector=query_embedding,
        top_k=top_k,
        score_threshold=score_threshold,
    )

    logger.info(f"Found {len(results)} relevant FAQs:\n")

    for idx, result in enumerate(results, 1):
        content = result.get("payload", {}).get("content", "")
        score = result.get("score", 0)
        logger.info(f"{idx}. [Score: {score:.3f}] {content}\n")

    return results


def test_search_queries():
    """Test various search queries."""
    test_queries = [
        ("How long does tire installation take?", "Should find document about 30-minute installation"),
        ("Can I get a refund?", "Should find refund policy (7 days)"),
        ("What is your warranty policy?", "Should find 3-year/30,000-mile warranty"),
        ("Winter tires availability", "Should find winter tire information"),
        ("Roadside assistance emergency", "Should find 24/7 hotline info"),
    ]

    logger.info("=" * 80)
    logger.info("TESTING SEARCH QUERIES")
    logger.info("=" * 80)

    for query, expected in test_queries:
        logger.info(f"\n{'─' * 80}")
        logger.info(f"Query: {query}")
        logger.info(f"Expected: {expected}")
        logger.info(f"{'─' * 80}")

        results = search_faq(query, top_k=3)

        if not results:
            logger.warning("⚠ No results found (may need to adjust score_threshold)")


def cleanup():
    """Delete test collection."""
    from services.tstation.rag import get_qdrant_service
    from config.env import settings

    logger.info("\nCleaning up test collection...")
    
    qdrant_svc = get_qdrant_service(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
    )
    
    try:
        qdrant_svc.delete_collection(settings.QDRANT_COLLECTION_FAQ)
        logger.info("✓ Test collection deleted")
    except Exception as e:
        logger.warning(f"Could not delete collection: {e}")


def main():
    """Main test flow."""
    logger.info("=" * 80)
    logger.info("RAG INTEGRATION TEST FOR FAQ SYSTEM")
    logger.info("=" * 80)

    try:
        # Setup
        logger.info("\n[SETUP] Initializing RAG services...")
        setup_rag()

        # Load test data
        logger.info("\n[DATA] Loading test FAQ documents...")
        documents = load_test_data()

        # Index documents
        logger.info("\n[INDEXING] Indexing documents into Qdrant...")
        index_documents(documents)

        # Test searches
        test_search_queries()

        logger.info("\n" + "=" * 80)
        logger.info("✓ ALL TESTS COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1

    finally:
        # Cleanup is optional - comment out to keep collection
        # cleanup()

        logger.info("\nNote: Qdrant collection persists. To clean up, call cleanup() or:")
        logger.info(f"  curl -X DELETE http://localhost:6333/collections/hankook_faq_docs")


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
