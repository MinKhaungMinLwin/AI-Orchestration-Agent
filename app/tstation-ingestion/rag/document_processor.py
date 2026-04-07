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

    # ---------------------------------------------------------------------------
    # Multi-vector helpers
    # ---------------------------------------------------------------------------

    # Korean particles to strip from keyword tokens (longest first)
    _KOREAN_PARTICLES: list[str] = [
        "으로부터", "로부터", "에게서", "에서부터",
        "이랑", "이라도", "이나마", "으로서", "이라서", "이라면",
        "에서", "까지", "부터", "에게", "한테", "처럼", "만큼",
        "보다", "마다", "조차", "라도", "나마", "으로", "로서",
        "이나", "이고", "와", "과", "나", "라", "고",
        "에", "의", "을", "를", "은", "는", "이", "가", "도", "만", "로",
    ]

    @staticmethod
    def normalize_korean_keyword(word: str) -> str:
        """Strip Korean grammatical particles from end of a single keyword token."""
        if not word:
            return word
        has_hangul = any("\uAC00" <= c <= "\uD7A3" for c in word)
        if not has_hangul:
            return word
        for particle in DocumentProcessor._KOREAN_PARTICLES:
            if word.endswith(particle) and len(word) > len(particle):
                return word[: -len(particle)]
        return word

    @staticmethod
    def normalize_keywords(keywords: list[str]) -> list[str]:
        """Return deduplicated, particle-stripped keywords."""
        seen: set[str] = set()
        result: list[str] = []
        for kw in keywords:
            normalized = DocumentProcessor.normalize_korean_keyword(kw.strip())
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    @staticmethod
    def build_embedding_texts(document: dict) -> tuple[str, str]:
        """
        Build (question_text, answer_text) for multi-vector embedding.

        question_text is augmented with intent + category for domain context.
        answer_text is augmented with normalized keywords to improve recall.
        """
        question = document.get("question", "")
        answer = document.get("answer", "")
        meta = document.get("metadata", {})

        intent = meta.get("intent", "")
        cat1 = meta.get("category_lv1", "")
        cat2 = meta.get("category_lv2", "")
        category = f"{cat1} > {cat2}".strip(" >") if cat2 else cat1

        # Augment question: [intent] category: question
        parts = []
        if intent:
            parts.append(f"[{intent}]")
        if category:
            parts.append(f"{category}:")
        parts.append(question)
        question_text = " ".join(parts)

        # Augment answer with normalized top keywords
        raw_keywords = meta.get("keywords", [])
        clean_kws = DocumentProcessor.normalize_keywords(raw_keywords)
        kw_str = " ".join(clean_kws[:6])
        answer_text = f"{answer}\n키워드: {kw_str}" if kw_str else answer

        return question_text, answer_text

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
