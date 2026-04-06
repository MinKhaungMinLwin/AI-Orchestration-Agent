"""
Document Processor for loading and preparing documents for RAG ingestion.

Supports:
- JSON document loading
- Text file processing
- Metadata extraction
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Processes and prepares documents for RAG indexing."""

    @staticmethod
    def load_json_documents(
        json_data: Optional[str | dict | list] = None,
        file_path: Optional[str] = None,
    ) -> list[dict]:
        """
        Load documents from JSON data or file.

        Args:
            json_data: JSON string or dict/list of documents
            file_path: Path to JSON file

        Returns:
            List of documents with normalized structure

        Example:
            # From dict
            docs = DocumentProcessor.load_json_documents(json_data=[
                {"id": 1, "content": "..."},
                {"id": 2, "content": "..."},
            ])

            # From file
            docs = DocumentProcessor.load_json_documents(file_path="faq.json")
        """
        documents = []

        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.exception(f"Failed to load JSON file: {file_path}")
                raise
        elif json_data:
            if isinstance(json_data, str):
                try:
                    data = json.loads(json_data)
                except json.JSONDecodeError as e:
                    logger.exception(f"Failed to parse JSON string")
                    raise
            else:
                data = json_data
        else:
            raise ValueError("Either json_data or file_path must be provided")

        # Normalize data to list
        if isinstance(data, dict):
            data = [data]
        elif not isinstance(data, list):
            raise ValueError("JSON data must be dict or list")

        # Normalize each document
        for idx, doc in enumerate(data):
            if not isinstance(doc, dict):
                raise ValueError(f"Document {idx} is not a dict: {type(doc)}")

            normalized = {
                "id": doc.get("id", idx),
                "content": doc.get("content", doc.get("text", "")),
                "metadata": {
                    "source": doc.get("source", "unknown"),
                    "timestamp": doc.get("timestamp", None),
                    **{
                        k: v
                        for k, v in doc.items()
                        if k not in ["id", "content", "text"]
                    },
                },
            }

            if not normalized["content"]:
                logger.warning(f"Document {idx} has empty content")

            documents.append(normalized)

        logger.info(f"Loaded {len(documents)} documents from JSON")
        return documents

    @staticmethod
    def load_text_documents(
        text_data: Optional[str] = None,
        file_path: Optional[str] = None,
        delimiter: str = "\n\n",
    ) -> list[dict]:
        """
        Load documents from plain text (split by delimiter).

        Args:
            text_data: Text string
            file_path: Path to text file
            delimiter: Delimiter to split documents (default: double newline)

        Returns:
            List of documents

        Example:
            docs = DocumentProcessor.load_text_documents(file_path="faq.txt")
        """
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text_data = f.read()
            except Exception as e:
                logger.exception(f"Failed to read text file: {file_path}")
                raise
        elif not text_data:
            raise ValueError("Either text_data or file_path must be provided")

        # Split by delimiter
        text_parts = text_data.split(delimiter)

        documents = [
            {
                "id": idx,
                "content": part.strip(),
                "metadata": {"source": file_path or "text_data"},
            }
            for idx, part in enumerate(text_parts)
            if part.strip()
        ]

        logger.info(f"Loaded {len(documents)} documents from text")
        return documents

    @staticmethod
    def prepare_for_indexing(
        documents: list[dict],
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> list[dict]:
        """
        Prepare documents for indexing: normalize + chunk.

        Args:
            documents: List of documents
            chunk_size: Chunk size in tokens
            chunk_overlap: Chunk overlap

        Returns:
            Chunked documents ready for embedding

        Example:
            docs = [{"id": 1, "content": "Long FAQ..."}, ...]
            prepared = DocumentProcessor.prepare_for_indexing(docs)
        """
        from services.tstation.rag.chunking import ChunkingService

        chunker = ChunkingService(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        all_chunks = []

        for doc in documents:
            doc_chunks = chunker.chunk_text(
                text=doc.get("content", ""),
                metadata={"original_id": doc.get("id"), **doc.get("metadata", {})},
            )
            all_chunks.extend(doc_chunks)

        logger.info(
            f"Prepared documents for indexing: "
            f"{len(documents)} docs -> {len(all_chunks)} chunks"
        )
        return all_chunks

    @staticmethod
    def print_doc_stats(documents: list[dict]) -> None:
        """Print statistics about documents."""
        if not documents:
            print("No documents")
            return

        total_tokens = sum(doc.get("token_count", 0) for doc in documents)
        avg_tokens = total_tokens / len(documents) if documents else 0

        print(f"Document Statistics:")
        print(f"  Total documents: {len(documents)}")
        print(f"  Total tokens: {total_tokens}")
        print(f"  Avg tokens/doc: {avg_tokens:.1f}")
        print(f"  First doc: {documents[0].get('content', '')[:100]}...")
