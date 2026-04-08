# RAG Integration Guide for T-Station Support Agent

## Overview

Hướng dẫn này giải thích cách triển khai **Retrieval-Augmented Generation (RAG)** cho FAQ Support Agent của T-Station Hankook Tire. RAG cho phép xử lý lượng lớn dữ liệu FAQ mà không bị giới hạn 200 ký tự của API cũ.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       User Query                              │
│                    "Do you offer refunds?"                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │    Support Agent receives query     │
        │     (e_support_agent/agent.py)       │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────────┐
        │   search_faq_rag_tool()                 │
        │  (e_support_agent/tools.py)             │
        └──────────────────┬──────────────────────┘
                           │
        ┌──────────────────▼──────────────────────┐
        │  1. Generate Query Embedding            │
        │     - Use OpenAI text-embedding-3-small  │
        │     - Convert query to vector (1536-D)   │
        └──────────────────┬──────────────────────┘
                           │
        ┌──────────────────▼──────────────────────┐
        │  2. Vector Search in Qdrant             │
        │     - Collection: hankook_faq_docs      │
        │     - Find top_k=5 similar documents    │
        │     - Filter by score_threshold=0.7     │
        └──────────────────┬──────────────────────┘
                           │
        ┌──────────────────▼──────────────────────┐
        │  3. Return Relevant FAQs                │
        │     - Content                            │
        │     - Similarity Score                   │
        │     - Metadata                           │
        └──────────────────┬──────────────────────┘
                           │
        ┌──────────────────▼──────────────────────┐
        │  4. LLM Synthesizes Answer              │
        │     - Uses retrieved FAQs as context    │
        │     - Generates natural response        │
        │     - Cites source documents            │
        └──────────────────┬──────────────────────┘
                           │
        ┌──────────────────▼──────────────────────┐
        │         User receives answer            │
        │    "Yes, we offer refunds within..."    │
        └──────────────────────────────────────────┘
```

## Step-by-Step Implementation

### Step 1️⃣: RAG Core Modules

**Files created:**
- `services/tstation/rag/qdrant_service.py` - Vector store operations
- `services/tstation/rag/embedding_service.py` - Embedding generation
- `services/tstation/rag/chunking.py` - Document chunking
- `services/tstation/rag/document_processor.py` - Document loading/processing
- `services/tstation/rag/__init__.py` - Module exports

#### 1.1 Qdrant Service (`qdrant_service.py`)
Manages Qdrant vector store operations:

```python
# Initialize
qdrant_svc = get_qdrant_service(
    host="localhost",
    port=6333,
)

# Create collection
qdrant_svc.create_collection(
    collection_name="hankook_faq_docs",
    vector_size=1536,  # OpenAI embedding size
)

# Index documents
qdrant_svc.upsert_documents(
    collection_name="hankook_faq_docs",
    documents=[
        {"id": 1, "content": "Refund policy...", "metadata": {...}},
        {"id": 2, "content": "Warranty...", "metadata": {...}},
    ],
    vectors=[
        [0.1, 0.2, ..., 0.9],  # Query embedding
        [0.3, 0.4, ..., 0.8],  # Query embedding
    ]
)

# Search
results = qdrant_svc.search(
    collection_name="hankook_faq_docs",
    query_vector=[0.1, 0.2, ..., 0.9],  # Query as vector
    top_k=5,
    score_threshold=0.7,
)
```

#### 1.2 Embedding Service (`embedding_service.py`)
Generates embeddings using OpenAI:

```python
embedding_svc = get_embedding_service(
    model="text-embedding-3-small",
    provider="openai",
)

# Embed single text
vector = embedding_svc.embed_text("Do you offer refunds?")
# Result: [0.1, 0.2, ..., 0.9] (1536 dimensions)

# Batch embed multiple texts
vectors = embedding_svc.embed_texts([
    "Do you offer refunds?",
    "What is warranty?",
    "How long does installation take?",
])
```

#### 1.3 Chunking Service (`chunking.py`)
Splits large documents into overlapping chunks:

```python
chunker = ChunkingService(
    chunk_size=512,      # tokens per chunk
    chunk_overlap=50,    # overlapping tokens
)

# Chunk single document
chunks = chunker.chunk_text(
    text="Long FAQ content here...",
    metadata={"source": "faq", "category": "warranty"}
)
# Result: [
#   {"id": "chunk_0", "content": "First 512 tokens...", "token_count": 512},
#   {"id": "chunk_1", "content": "Next 512 tokens with 50 overlap...", "token_count": 512},
# ]
```

#### 1.4 Document Processor (`document_processor.py`)
Loads and processes documents:

```python
# Load from JSON
documents = DocumentProcessor.load_json_documents(
    file_path="faq_test_data.json"
)

# Or from text
documents = DocumentProcessor.load_text_documents(
    file_path="faq.txt",
    delimiter="\n\n"
)

# Prepare for indexing (normalize + chunk)
prepared_docs = DocumentProcessor.prepare_for_indexing(
    documents=documents,
    chunk_size=512,
    chunk_overlap=50,
)
```

### Step 2️⃣: Configuration

**Update `config/env.py`:**
```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    ### RAG (Retrieval-Augmented Generation)
    QDRANT_HOST: str = Field(default="localhost")
    QDRANT_PORT: int = Field(default=6333)
    QDRANT_API_KEY: str = Field(default="")
    QDRANT_COLLECTION_FAQ: str = Field(
        default="hankook_faq_docs",
    )
    EMBEDDING_PROVIDER: str = Field(default="openai")
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small")
    RAG_CHUNK_SIZE: int = Field(default=512)
    RAG_CHUNK_OVERLAP: int = Field(default=50)
    RAG_SEARCH_TOP_K: int = Field(default=5)
    RAG_SEARCH_SCORE_THRESHOLD: float = Field(default=0.7)
```

**Update `.env`:**
```bash
### RAG
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=
QDRANT_COLLECTION_FAQ=hankook_faq_docs
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=50
RAG_SEARCH_TOP_K=5
RAG_SEARCH_SCORE_THRESHOLD=0.7
```

### Step 3️⃣: Support Agent Tool

**Updated `tools.py` - `search_faq_rag_tool`:**

```python
@tool
def search_faq_rag_tool(
    query: str, 
    top_k: int = 5, 
    score_threshold: float = 0.7
) -> dict:
    """
    Search FAQs using RAG.
    
    Args:
        query: User's question
        top_k: Number of results (default 5)
        score_threshold: Min similarity score (default 0.7)
    
    Returns:
        {"status": "success", "http_status": 200, "data": [...]}
    """
    try:
        # 1. Generate query embedding
        embedding_service = get_embedding_service(
            model=settings.EMBEDDING_MODEL,
            provider=settings.EMBEDDING_PROVIDER,
        )
        query_embedding = embedding_service.embed_text(query)
        
        # 2. Search in Qdrant
        qdrant_service = get_qdrant_service(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
        search_results = qdrant_service.search(
            collection_name=settings.QDRANT_COLLECTION_FAQ,
            query_vector=query_embedding,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        
        # 3. Format results
        formatted_results = [
            {
                "id": result["id"],
                "score": result["score"],
                "content": result["payload"]["content"],
                "metadata": result["payload"]["metadata"],
            }
            for result in search_results
        ]
        
        return {"status": "success", "http_status": 200, "data": formatted_results}
        
    except Exception as e:
        return {"status": "error", "http_status": None, "reason": str(e)}
```

**Updated `agent.py`:**

```python
from services.tstation.agents.e_support_agent.tools import (
    search_faq_rag_tool,  # ← Changed from get_faq_tool
    transfer_to_qna_tool,
)

SUPPORT_AGENT_SYSTEM_PROMPT = f"""
...
TOOLS:
- search_faq_rag_tool: Search FAQ database using RAG
...
"""

class SupportSubAgent(BaseAgent):
    TOOL_TO_AF_MAP = {
        "search_faq_rag_tool": "FAQ (RAG Search)",  # ← Updated
        "transfer_to_qna_tool": "1:1 Inquiry Transfer",
    }

    def __init__(self, model):
        super().__init__(
            model=model,
            tools=[
                search_faq_rag_tool,  # ← Changed from get_faq_tool
                transfer_to_qna_tool,
            ],
            system_prompt=SUPPORT_AGENT_SYSTEM_PROMPT,
            name="Support Agent",
        )
```

### Step 4️⃣: Testing with Sample Data

#### 4.1 Run Qdrant locally

```bash
# Start Qdrant in Docker
docker-compose -f docker_local/docker-compose-llm.yml up qdrant

# Verify it's running (should return {"status":"ok"})
curl http://localhost:6333/health
```

#### 4.2 Run test script

```bash
# From project root
python example/tstation-ai/test_rag_integration.py
```

Expected output:
```
[INFO] Loaded 10 FAQ documents from faq_test_data.json
[INFO] Qdrant connected: localhost:6333
[INFO] Embedding service ready: text-embedding-3-small
[INFO] Step 1: Creating Qdrant collection...
[INFO] Step 2: Processing documents...
[INFO] → 10 chunks created from 10 documents
[INFO] Step 3: Generating embeddings...
[INFO] → Generated 10 embeddings
[INFO] Step 4: Indexing into Qdrant...
[INFO] ✓ Indexed: 10 documents

[INFO] Searching for: 'How long does tire installation take?'
[INFO] Found 3 relevant FAQs:

1. [Score: 0.856] Tire installation takes about 30 minutes.
2. [Score: 0.742] Our winter tire collection is available from September to April...
3. [Score: 0.698] Tire rotation is recommended every 6,000 to 8,000 miles...
```

## Complete Integration Flow

### 1. Document Ingestion Pipeline

```python
# 1. Client sends FAQ documents
documents = [
    {"id": 1, "content": "Refund policy...", "metadata": {...}},
    {"id": 2, "content": "Warranty...", "metadata": {...}},
    # ... more documents
]

# 2. Process & chunk documents
from services.tstation.rag import DocumentProcessor
prepared_docs = DocumentProcessor.prepare_for_indexing(
    documents=documents,
    chunk_size=512,
    chunk_overlap=50,
)

# 3. Generate embeddings
from services.tstation.rag import get_embedding_service
embedding_svc = get_embedding_service()
vectors = embedding_svc.embed_texts([doc["content"] for doc in prepared_docs])

# 4. Index into Qdrant
from services.tstation.rag import get_qdrant_service
qdrant_svc = get_qdrant_service()
qdrant_svc.upsert_documents(
    collection_name="hankook_faq_docs",
    documents=prepared_docs,
    vectors=vectors,
)
```

### 2. User Query Flow

```python
# User: "Do you offer refunds?"
# ↓
# Support Agent calls search_faq_rag_tool("Do you offer refunds?")
# ↓
# Tool returns:
# {
#   "status": "success",
#   "data": [
#       {"id": 2, "score": 0.89, "content": "Customers can request refunds..."},
#       {"id": 5, "score": 0.78, "content": "You can exchange tires within 14 days..."},
#   ]
# }
# ↓
# LLM combines results + generates answer:
# "Yes! Customers can request refunds within 7 days of purchase. 
#  We also offer tire exchanges within 14 days if you're not satisfied."
```

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `QDRANT_HOST` | Qdrant server host | localhost |
| `QDRANT_PORT` | Qdrant server port | 6333 |
| `QDRANT_API_KEY` | API key (if secured) | (empty) |
| `QDRANT_COLLECTION_FAQ` | Collection name | hankook_faq_docs |
| `EMBEDDING_PROVIDER` | openai / cohere | openai |
| `EMBEDDING_MODEL` | Model name | text-embedding-3-small |
| `RAG_CHUNK_SIZE` | Tokens per chunk | 512 |
| `RAG_CHUNK_OVERLAP` | Overlapping tokens | 50 |
| `RAG_SEARCH_TOP_K` | Number of results | 5 |
| `RAG_SEARCH_SCORE_THRESHOLD` | Min relevance score | 0.7 |

### Embedding Models Comparison

| Model | Provider | Dimensions | Speed | Cost |
|-------|----------|-----------|-------|------|
| text-embedding-3-small | OpenAI | 1536 | Fast | Low ✓ |
| text-embedding-3-large | OpenAI | 3072 | Slow | High |
| embed-english-v3.0 | Cohere | 1024 | Fast | Low |
| embed-english-light-v3.0 | Cohere | 384 | Very Fast | Very Low |

**Recommendation:** Use `text-embedding-3-small` (good balance of quality & cost)

## Troubleshooting

### Problem: "Qdrant server is not accessible"
```bash
# Solution: Start Qdrant
docker-compose -f docker_local/docker-compose-llm.yml up qdrant

# Verify connection
curl http://localhost:6333/health
```

### Problem: "Embedding service is not accessible"
```bash
# Check OPENAI_API_KEY in .env
echo $OPENAI_API_KEY

# Solution: Set API key
export OPENAI_API_KEY=sk-your-key-here
```

### Problem: Search returns no results
1. Check collection has documents:
   ```bash
   curl http://localhost:6333/collections/hankook_faq_docs
   ```

2. Lower score_threshold (default 0.7):
   ```python
   search_faq_rag_tool(query="...", score_threshold=0.5)
   ```

3. Increase top_k:
   ```python
   search_faq_rag_tool(query="...", top_k=10)
   ```

## File Structure

```
app/tstation-ai/
├── services/tstation/
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── qdrant_service.py      ← Vector store
│   │   ├── embedding_service.py   ← Embeddings
│   │   ├── chunking.py            ← Document chunking
│   │   └── document_processor.py  ← Load/process docs
│   └── agents/
│       └── e_support_agent/
│           ├── agent.py           ← Updated
│           └── tools.py           ← Updated
├── config/
│   └── env.py                     ← Updated
└── ...

example/tstation-ai/
├── faq_test_data.json             ← Test data
└── test_rag_integration.py        ← Test script
```

## Next Steps

1. **Deploy Qdrant in production:**
   - Use Docker in cloud (AWS, GCP, Azure)
   - Or use Qdrant Cloud (hosted service)

2. **Add document ingestion API:**
   ```python
   @router.post("/tstation/ingest-faq")
   async def ingest_faq_documents(files: List[UploadFile]):
       # Load files
       # Process documents
       # Index into Qdrant
   ```

3. **Add collection management:**
   - Delete old collections
   - Backup vectors
   - Monitor collection size

4. **Optimize performance:**
   - Batch embedding generation
   - Cache frequently asked queries
   - Use smaller embeddings (384-D with Cohere)

## References

- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [OpenAI Embeddings](https://platform.openai.com/docs/guides/embeddings)
- [LangChain RAG](https://python.langchain.com/docs/use_cases/retrieval_augmented_generation)
- [Project Architecture](../../docs/system-architecture.md)

---

**Completed! Your RAG-powered FAQ system is ready to handle unlimited FAQ content.**
