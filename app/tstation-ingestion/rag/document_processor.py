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

            normalized = DocumentProcessor._normalize_document(doc, idx)

            if not normalized["question"] and not normalized["answer"]:
                logger.warning(f"Document {idx} (id={normalized['id']}) has no question or answer text")

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
    # Document normalization — unify different source schemas
    # ---------------------------------------------------------------------------

    # Candidate field names for each logical field, tried in order
    _QUESTION_FIELDS: list[str] = ["question", "representative_question"]
    _ANSWER_FIELDS: list[str]   = ["answer",   "representative_answer"]
    _CONTENT_FIELDS: list[str]  = ["content",  "text", "body"]

    @staticmethod
    def _resolve_field(doc: dict, candidates: list[str]) -> str:
        """Return the first non-empty string value found among candidate keys."""
        for key in candidates:
            val = doc.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    @staticmethod
    def _normalize_document(doc: dict, idx: int) -> dict:
        """
        Convert any supported raw document format into a unified schema.

        Supported source formats:
          - Type 1: {question, answer, content, metadata: {intent, keywords, ...}}
          - Type 2: {representative_question, representative_answer, similar_questions,
                     metadata: {category_lv1, category_lv2}}
          - Any future format that uses _QUESTION_FIELDS / _ANSWER_FIELDS variants

        Output schema:
          {
            id, question, answer, content,
            similar_questions: list[str],
            metadata: {category_lv1, category_lv2, intent, keywords, source, lang, document_type, ...}
          }
        """
        dp = DocumentProcessor

        question = dp._resolve_field(doc, dp._QUESTION_FIELDS)
        answer   = dp._resolve_field(doc, dp._ANSWER_FIELDS)

        # Build `content` from question+answer when not explicitly provided
        content = dp._resolve_field(doc, dp._CONTENT_FIELDS)
        if not content:
            parts = []
            if question:
                parts.append(f"질문: {question}")
            if answer:
                parts.append(f"답변: {answer}")
            content = "\n".join(parts)

        # Collect similar_questions (Type 2 field, empty list for Type 1)
        similar_questions: list[str] = [
            q for q in doc.get("similar_questions", [])
            if isinstance(q, str) and q.strip()
        ]

        # Merge metadata — raw metadata block takes priority over top-level fields
        raw_meta: dict = doc.get("metadata", {})
        meta = {
            "category_lv1":  raw_meta.get("category_lv1", ""),
            "category_lv2":  raw_meta.get("category_lv2", ""),
            "intent":        raw_meta.get("intent", ""),
            "keywords":      raw_meta.get("keywords", []),
            "source":        raw_meta.get("source", doc.get("source", "unknown")),
            "lang":          raw_meta.get("lang", "ko"),
            "document_type": raw_meta.get("document_type", "faq_qa"),
        }
        # Preserve any extra keys from raw_meta not already captured
        for k, v in raw_meta.items():
            if k not in meta:
                meta[k] = v

        return {
            "id":               doc.get("id", idx),
            "question":         question,
            "answer":           answer,
            "content":          content,
            "similar_questions": similar_questions,
            "metadata":         meta,
        }

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

        Works with the unified schema produced by _normalize_document:
          - question_text: [intent] category: question + similar_questions (Type 2)
          - answer_text:   answer + normalized keywords (Type 1) or category context (Type 2)

        Documents must be normalized via _normalize_document before calling this.
        """
        question = document.get("question", "")
        answer   = document.get("answer", "")
        similar_questions: list[str] = document.get("similar_questions", [])
        meta = document.get("metadata", {})

        intent = meta.get("intent", "")
        cat1   = meta.get("category_lv1", "")
        cat2   = meta.get("category_lv2", "")
        category = f"{cat1} > {cat2}".strip(" >") if cat2 else cat1

        # --- question_text ---
        parts = []
        if intent:
            parts.append(f"[{intent}]")
        if category:
            parts.append(f"{category}:")
        if question:
            parts.append(question)
        # Append similar_questions (Type 2) for multi-surface coverage
        if similar_questions:
            parts.append("유사 질문: " + " / ".join(similar_questions[:5]))
        question_text = " ".join(parts)

        # --- answer_text ---
        raw_keywords = meta.get("keywords", [])
        clean_kws = DocumentProcessor.normalize_keywords(raw_keywords)
        kw_str = " ".join(clean_kws[:6])
        if kw_str:
            answer_text = f"{answer}\n키워드: {kw_str}"
        elif category:
            # Type 2 has no keywords — append category as fallback context
            answer_text = f"{answer}\n카테고리: {category}"
        else:
            answer_text = answer

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
