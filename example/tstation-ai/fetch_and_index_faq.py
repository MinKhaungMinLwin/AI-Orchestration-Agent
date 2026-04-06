#!/usr/bin/env python3
"""
Fetch FAQ data from backend API and index to Qdrant.
Combines: fetch → transform → index in one command.
"""

import json
import sys
import logging
from pathlib import Path
from typing import Optional

# Setup path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "app" / "tstation-ai"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_faq_from_backend(
    api_url: str = "http://localhost:8000/api/faq",
    limit: int = 200,
    timeout: int = 10
) -> Optional[dict]:
    """Fetch FAQ from backend API."""
    try:
        import requests
        logger.info(f"📡 Fetching FAQs from {api_url}?limit={limit}...")
        
        response = requests.get(
            api_url,
            params={"limit": limit},
            timeout=timeout
        )
        response.raise_for_status()
        
        data = response.json()
        total = data.get("total", 0)
        items = data.get("items", [])
        
        logger.info(f"✅ Fetched {len(items)} FAQs (total: {total})")
        return {
            "total": total,
            "items": items[:limit]  # Limit to requested number
        }
    except Exception as e:
        logger.error(f"❌ Failed to fetch FAQs: {e}")
        return None


def convert_to_test_format(api_response: dict) -> list[dict]:
    """Convert API response to test format."""
    test_data = []
    
    items = api_response.get("items", [])
    for idx, item in enumerate(items, start=1):
        question = item.get("cust_quest", "").strip()
        answer = item.get("pc_ans_cont", "").strip()
        category = f"{item.get('lrcl_cd', 'N/A')}-{item.get('mdcl_cd', 'N/A')}"
        
        # Clean HTML
        answer_clean = answer.replace("<br />", " ").replace("<br/>", " ")
        answer_clean = answer_clean.replace("<font color=\"blue\">", "").replace("</font>", "")
        answer_clean = answer_clean.replace("▶", "").replace("&nbsp;", " ")
        answer_clean = answer_clean.strip()
        
        content = f"Q: {question}\nA: {answer_clean}\nCategory: {category}"
        
        test_data.append({
            "id": idx,
            "content": content,
        })
    
    return test_data


def index_to_qdrant(test_data: list[dict]) -> bool:
    """Index test data to Qdrant."""
    try:
        from config.env import settings
        from services.tstation.rag import (
            get_embedding_service,
            get_qdrant_service,
            get_document_processor,
        )
        import os
        
        logger.info(f"📚 Indexing {len(test_data)} FAQs to Qdrant...")
        
        # Get API key
        api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
        if not api_key:
            logger.error("❌ OPENAI_API_KEY not set")
            return False
        
        # Initialize services
        embedding_service = get_embedding_service(
            model=settings.EMBEDDING_MODEL,
            provider=settings.EMBEDDING_PROVIDER,
            api_key=api_key,
        )
        
        qdrant_service = get_qdrant_service(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY or None,
        )
        
        processor = get_document_processor()
        
        # Create collection if not exists
        qdrant_service.create_collection(
            collection_name=settings.QDRANT_COLLECTION_FAQ
        )
        
        # Chunk documents
        chunks = processor.prepare_for_indexing(test_data)
        logger.info(f"📦 Created {len(chunks)} chunks from {len(test_data)} documents")
        
        # Generate embeddings and index
        contents = [chunk["content"] for chunk in chunks]
        embeddings = embedding_service.embed_texts(contents)
        
        # Prepare points for Qdrant
        points = [
            {
                "id": idx,
                "vector": embedding,
                "payload": {
                    "content": chunk["content"],
                    "metadata": chunk.get("metadata", {}),
                }
            }
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        
        # Upload to Qdrant
        qdrant_service.upsert_documents(
            collection_name=settings.QDRANT_COLLECTION_FAQ,
            points=points,
        )
        
        logger.info(f"✅ Indexed {len(points)} vectors to Qdrant")
        return True
        
    except Exception as e:
        logger.exception(f"❌ Failed to index to Qdrant: {e}")
        return False


def main():
    """Fetch → Transform → Index workflow."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch FAQ and index to Qdrant")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000/api/faq",
        help="FAQ API endpoint"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max FAQs to fetch"
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save converted data to faq_test_data.json"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("📋 FAQ FETCH & INDEX WORKFLOW")
    logger.info("=" * 60)
    
    # Step 1: Fetch
    api_response = fetch_faq_from_backend(
        api_url=args.api_url,
        limit=args.limit
    )
    if not api_response:
        logger.error("Exiting: Failed to fetch FAQs")
        return 1
    
    # Step 2: Transform
    test_data = convert_to_test_format(api_response)
    logger.info(f"✅ Converted {len(test_data)} FAQs to test format")
    
    # Optional: Save JSON
    if args.save_json:
        output_file = Path(__file__).parent / "faq_test_data.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Saved to {output_file}")
    
    # Step 3: Index
    success = index_to_qdrant(test_data)
    
    logger.info("=" * 60)
    if success:
        logger.info("✅ WORKFLOW COMPLETED SUCCESSFULLY")
        logger.info("FAQ data is now indexed and ready for RAG search")
    else:
        logger.error("❌ WORKFLOW FAILED")
    logger.info("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
