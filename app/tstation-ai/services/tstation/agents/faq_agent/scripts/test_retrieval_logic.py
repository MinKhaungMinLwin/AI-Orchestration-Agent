# scripts/test_retrieval_logic.py
import sys
import os
import time

# 1. Setup paths to allow importing from 'shared' and 'config'
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from config.settings import settings
from shared import vector_store, llm_client

def run_retrieval_test():
    print("\n" + "="*60)
    print("🔬 ISOLATED RETRIEVAL TEST")
    print("="*60)

    # ---------------------------------------------------------
    # 1. CONFIGURATION CHECK
    # ---------------------------------------------------------
    print(f"1️⃣  CONFIGURATION CHECK")
    print(f"   - Target Collection (Settings): '{settings.qdrant_collection_faq}'")
    print(f"   - Embedding Model: {settings.openai_embedding_model}")
    
    # ---------------------------------------------------------
    # 2. DATABASE STATUS CHECK
    # ---------------------------------------------------------
    print(f"\n2️⃣  DATABASE STATUS")
    try:
        # Check if collection exists
        col_info = vector_store.client.get_collection(settings.qdrant_collection_faq)
        print(f"   - Collection '{settings.qdrant_collection_faq}' Status: FOUND ✅")
        print(f"   - Total Vectors: {col_info.points_count}")
        print(f"   - Vector Size: {col_info.config.params.vectors.size}")
        
        if col_info.points_count == 0:
            print("\n❌ CRITICAL ERROR: Collection is empty. Search will always fail.")
            print("   Action: Run 'python scripts/load_faqs_to_qdrant.py' again.")
            return
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Collection '{settings.qdrant_collection_faq}' NOT FOUND.")
        print(f"   Error details: {e}")
        print("\n   Action: Check your .env file. QDRANT_COLLECTION_FAQ might be wrong.")
        
        # List available collections to help debug
        try:
            cols = vector_store.client.get_collections().collections
            print(f"   Available collections: {[c.name for c in cols]}")
        except:
            pass
        return

    # ---------------------------------------------------------
    # 3. EMBEDDING GENERATION CHECK
    # ---------------------------------------------------------
    query = "배송 기간은 얼마나 걸리나요?"
    print(f"\n3️⃣  EMBEDDING GENERATION")
    print(f"   - Test Query: '{query}'")
    
    try:
        query_vector = llm_client.embed(query)
        dim = len(query_vector)
        print(f"   - Generated Vector Dimension: {dim}")
        
        # Check for dimension mismatch
        db_dim = col_info.config.params.vectors.size
        if dim != db_dim:
            print(f"\n❌ CRITICAL ERROR: Dimension Mismatch!")
            print(f"   - Database expects: {db_dim}")
            print(f"   - Embedding model produced: {dim}")
            print("   Action: You likely loaded data with 'large' model but are searching with 'small' (or vice versa).")
            print("   Update 'OPENAI_EMBEDDING_MODEL' in .env to match.")
            return
            
    except Exception as e:
        print(f"❌ Error generating embedding: {e}")
        return

    # ---------------------------------------------------------
    # 4. SEARCH EXECUTION (The Core Test)
    # ---------------------------------------------------------
    print(f"\n4️⃣  EXECUTING SEARCH")
    
    try:
        # Perform search using the SHARED function (exactly what the agent uses)
        results = vector_store.search_faqs(query, top_k=3)
        
        print(f"   - Search Function Returned: {len(results)} results")
        
        if len(results) > 0:
            print("\n✅ SUCCESS! Retrieval is working.")
            print("-" * 30)
            for i, res in enumerate(results):
                print(f"   Result #{i+1} (Score: {res['similarity_score']:.4f})")
                print(f"   Q: {res['cust_quest']}")
                print(f"   A: {res['pc_ans_cont'][:50]}...")
                print("-" * 30)
        else:
            print("\n⚠️  WARNING: Function returned 0 results.")
            
            # ---------------------------------------------------------
            # 5. DEEP DIVE DEBUG (If search failed)
            # ---------------------------------------------------------
            print("\n5️⃣  DEEP DIVE: RAW SEARCH (No Threshold)")
            print("   Attempting raw search directly on Qdrant client...")
            
            raw_hits = vector_store.client.search(
                collection_name=settings.qdrant_collection_faq,
                query_vector=query_vector,
                limit=3,
                score_threshold=0.0 # FORCE NO THRESHOLD
            )
            
            if len(raw_hits) > 0:
                print(f"   ✅ Raw search FOUND {len(raw_hits)} hits (ignored by application threshold).")
                print(f"   Top Score: {raw_hits[0].score:.4f}")
                print("\n   Action: Your data exists, but the score is too low.")
                print("   1. Lower the threshold in 'shared/vector_store.py'.")
                print("   2. Check if your query language matches the data language.")
            else:
                print("   ❌ Raw search also returned 0 hits.")
                print("   Action: The vectors in the DB might be corrupted or zero-vectors.")

    except Exception as e:
        print(f"❌ Error during search: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Ensure no other process (like uvicorn) is locking the file
    print("Checking for existing locks...")
    run_retrieval_test()