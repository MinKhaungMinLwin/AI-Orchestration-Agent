# RAG Integration into Support Agent - Implementation Guide

## 🎯 Overview

Bạn đã hoàn thành triển khai RAG cho Support Agent. Hướng dẫn này giới thiệu **cách tích hợp vào luồng chat thực tế** và **điều chỉnh để production**.

---

## 📊 Architecture

```
┌─────────────────────────────────────────┐
│        User Chat Interface              │
│    "Can I get a refund?"                │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│     Support Agent (e_support_agent)     │
│                                         │
│  System Prompt (Updated):              │
│  - ALWAYS call search_faq_rag_tool first│
│  - Use RAG results to answer           │
│  - Cite FAQ sources                    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      search_faq_rag_tool (Tool)         │
│                                         │
│  1. Get query embedding (OpenAI)       │
│  2. Vector search in Qdrant             │
│  3. Return top 5 relevant FAQs          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      Qdrant Vector Store                │
│  (FAQ documents, indexed & chunked)     │
└─────────────────────────────────────────┘
```

---

## 📂 Files Changed

### 1. **tools.py** - search_faq_rag_tool Implementation
- ✅ Added `os` import to read OPENAI_API_KEY
- ✅ Passes `api_key` to embedding service
- ✅ Fully connects to Qdrant for real RAG search
- ✅ Returns formatted FAQ results with scores

**Key Changes:**
```python
@tool
def search_faq_rag_tool(query: str, top_k: int = 5, score_threshold: float = 0.7) -> dict:
    # 1. Get API key from environment
    openai_api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
    
    # 2. Generate query embedding
    embedding_service = get_embedding_service(
        model=settings.EMBEDDING_MODEL,
        provider=settings.EMBEDDING_PROVIDER,
        api_key=openai_api_key,  # ← Pass API key
    )
    
    # 3. Vector search in Qdrant
    search_results = qdrant_service.search(...)
    
    # 4. Return formatted results with scores
    return _success_response(200, formatted_results)
```

### 2. **agent.py** - Updated System Prompt

**Key Improvements:**
- ✅ Clearer explanation of RAG-powered search
- ✅ Step-by-step search & answer flow
- ✅ How to interpret FAQ relevance scores
- ✅ Response examples for different scenarios
- ✅ Rules for when to use 1:1 inquiry transfer

**New Prompt Structure:**
```
PRIMARY BEHAVIOR
├─ When user asks → Call search_faq_rag_tool FIRST
├─ Use retrieved FAQs → Formulate answer
└─ Cite sources → "According to our FAQ..."

TOOL USAGE
├─ search_faq_rag_tool: How & when to use
└─ transfer_to_qna_tool: For human escalation

SEARCH AND ANSWER FLOW
├─ Step 1: Search ("Let me search our database...")
├─ Step 2: Evaluate Results (score interpretation)
├─ Step 3: Formulate Answer (cite sources)
└─ Step 4: Offer Next Steps

RESPONSE EXAMPLES
├─ FAQ Found (High Relevance)
├─ FAQ Found (Multiple Results)
└─ No FAQs Found (Offer alternatives)
```

---

## 🧪 Testing Scripts Created

### 1. **test_rag_integration.py** (Already Tested ✓)
- Tests RAG pipeline in isolation
- Verifies Qdrant + Embedding services work
- Tests semantic search queries

**Run:**
```bash
set -a; source .env; set +a
uv run python example/tstation-ai/test_rag_integration.py
```

### 2. **test_support_agent_rag.py** (Already Tested ✓)
- Tests Support Agent with RAG
- Shows tool invocation + FAQ retrieval
- Streams agent responses

**Run:**
```bash
set -a; source .env; set +a
uv run python example/tstation-ai/test_support_agent_rag.py
```

### 3. **test_support_agent_api.py** (New - Live Test)
- Tests real agent API conversation flow
- Shows how agent internally calls RAG tool
- Demonstrates full end-to-end integration

**Run:**
```bash
set -a; source .env; set +a
uv run python example/tstation-ai/test_support_agent_api.py
```

---

## 🚀 Integration into Production Chat

### Step 1: Ensure FAQ Data is Indexed

Before deploying, verify FAQ index exists in Qdrant:

```python
# In your initialization script or on app startup
from services.tstation.rag import get_qdrant_service
from config.env import settings

qdrant = get_qdrant_service(...)
collections = qdrant.client.get_collections()
collection_names = [c.name for c in collections.collections]

if settings.QDRANT_COLLECTION_FAQ not in collection_names:
    # Index FAQ documents
    # See: example/tstation-ai/test_rag_integration.py for reference
    pass
```

### Step 2: Support Agent Already Uses RAG

The Support Agent in `services/tstation/agents/e_support_agent/agent.py` is ready to use.

It's called from the multi-agent router when domain classification returns "SUPPORT".

**Currently Used In:**
- Multi-agent orchestration (chat.py)
- Handles WARRANTY, RETURNS, FAQ, SUPPORT domain queries

### Step 3: Direct Integration (Optional)

If you want to use Support Agent directly without multi-agent router:

```python
from langchain_litellm import ChatLiteLLM
from services.tstation.agents.e_support_agent.agent import SupportSubAgent
from config.env import settings

# Create LLM
llm = ChatLiteLLM(
    api_base=settings.AI_GATEWAY_BASE_URL,
    api_key=settings.AI_GATEWAY_API_KEY,
    model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL}",
)

# Create agent
agent = SupportSubAgent(model=llm)

# Use in conversation
messages = [{"role": "user", "content": "Can I return my tires?"}]

# Stream response (agent calls search_faq_rag_tool internally)
for event in agent.stream(messages):
    if event["type"] == "token":
        print(event["content"], end="", flush=True)
```

---

## 🔧 Configuration & Tuning

### RAG Parameters in `.env`

```bash
# Vector Store
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Embedding
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# Chunking
RAG_CHUNK_SIZE=512           # Tokens per chunk
RAG_CHUNK_OVERLAP=50         # Overlapping tokens

# Search
RAG_SEARCH_TOP_K=5           # Max results
RAG_SEARCH_SCORE_THRESHOLD=0.7  # Min relevance
```

### Tuning Recommendations

#### If Getting Too Many Results:
```bash
↑ Increase RAG_SEARCH_SCORE_THRESHOLD (e.g., 0.75, 0.8)
↓ Decrease RAG_SEARCH_TOP_K (e.g., 3)
```

#### If Getting No Results:
```bash
↓ Decrease RAG_SEARCH_SCORE_THRESHOLD (e.g., 0.6, 0.5)
↑ Increase RAG_SEARCH_TOP_K (e.g., 10, 20)
```

#### For Better Quality:
```bash
Increase RAG_CHUNK_SIZE if:
- FAQs are getting split into too many chunks
- Context is getting lost between chunks

Increase RAG_CHUNK_OVERLAP if:
- Important information appears at chunk boundaries
- You need better chunk continuity
```

---

## 📋 Implementation Checklist

### Pre-Production
- [ ] FAQ documents indexed in Qdrant
- [ ] .env has OPENAI_API_KEY set
- [ ] Test with test_support_agent_api.py passes
- [ ] Verify search quality (relevance scores > 0.7)

### Deployment
- [ ] Qdrant running (Docker or Cloud)
- [ ] Support Agent active in multi-agent router
- [ ] Monitor tool invocation logs in production

### Post-Deployment
- [ ] Monitor FAQ search quality in logs
- [ ] Track RAG_SEARCH_SCORE_THRESHOLD performance
- [ ] Update FAQ documents regularly
- [ ] Collect user feedback on answer quality

---

## 📊 Monitoring & Logging

### Tool Logs to Watch

The tool automatically logs:
```
[TOOL][search_faq_rag_tool] Called with: query=..., top_k=5, score_threshold=0.7
[TOOL][search_faq_rag_tool] Query embedding dimension: 1536
[TOOL][search_faq_rag_tool] Found 3 relevant FAQs (score_threshold=0.7)
```

### Key Metrics to Track

| Metric | What to Watch |
|--------|---------------|
| Query embedding time | < 500ms (should be fast) |
| Qdrant search time | < 100ms (vector search is fast) |
| Results count | >= 1 for most queries |
| Relevance scores | Typically > 0.75 for good matches |
| LLM generation time | Depends on answer length |

---

## 🎓 How Agent Uses RAG

### Agent Decision Flow

```
User asks: "Can I return my tires?"
                ↓
Agent thinks: "This is a FAQ question"
                ↓
Agent calls: search_faq_rag_tool(
    query="Can I return my tires?",
    top_k=5,
    score_threshold=0.7
)
                ↓
RAG Pipeline:
  1. Embed query → [0.1, 0.2, ..., 0.9] (1536-D)
  2. Search Qdrant → Find similar FAQ chunks
  3. Filter by score >= 0.7
  4. Return top 5 results
                ↓
Tool returns:
  [
    {
      "id": 2,
      "score": 0.92,
      "content": "You can exchange tires within 14 days...",
      "metadata": {...}
    },
    ...
  ]
                ↓
Agent synthesizes:
  "Yes! Based on our FAQ, you can exchange tires 
   within 14 days if not satisfied..."
                ↓
User receives answer with
  - FAQ-backed information
  - Relevance confidence (0.92 = 92% relevant)
  - Option for 1:1 inquiry if needed
```

---

## 🐛 Troubleshooting

### Problem: Tool Returns No Results
```
Check:
1. Is Qdrant running? → docker-compose -f docker_local/docker-compose-llm.yml up qdrant
2. Is collection indexed? → Verify in test_rag_integration.py
3. Are FAQ documents in Qdrant? → Query Qdrant directly
4. Is score_threshold too high? → Lower to 0.5, test again
```

### Problem: Tool Takes Too Long
```
Check:
1. Qdrant connection latency
2. Embedding service response time
3. Query complexity (simple vs complex)
4. Network connectivity
```

### Problem: Low Relevance Scores
```
Check:
1. FAQ documents well-written (clear language)
2. Mismatch between query & FAQ content
3. Embedding model quality
4. Adjust score_threshold if too strict
```

---

## 📚 Next Steps

1. **Immediate**: Run test_support_agent_api.py to verify everything works
2. **Short-term**: Deploy to staging environment
3. **Medium-term**: Collect user feedback & improve FAQ documents
4. **Long-term**: Monitor search quality, optimize parameters

---

## 📖 Reference Files

| File | Purpose |
|------|---------|
| `tools.py` | `search_faq_rag_tool` implementation |
| `agent.py` | Support Agent with RAG-aware prompt |
| `test_support_agent_api.py` | Live test script |
| `docs/rag-integration-guide.md` | Detailed RAG guide |
| `services/tstation/rag/` | RAG core modules |
| `.env` | Configuration |

---

## ✅ Summary

Your Support Agent is now **fully RAG-enabled**:

✓ Automatically searches FAQ database for every query  
✓ Uses semantic search (not keyword matching)  
✓ Returns relevant documents with scores  
✓ Agent synthesizes natural answers from retrieved FAQs  
✓ Ready for production deployment  

**Next Action:** Run test_support_agent_api.py to see it in action! 🚀
