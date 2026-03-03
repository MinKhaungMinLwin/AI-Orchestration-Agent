# scripts/load_faqs_to_qdrant.py
"""
Production script to load FAQs from company database to Qdrant
Supports Oracle, PostgreSQL, MySQL
"""
import asyncio
import sys
import os

#sys.path.insert(0, '/app')

# Get the absolute path to the project root (one level up from scripts/)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from shared import vector_store
from config.settings import settings
# import directly from oracledb
import oracledb

async def load_faqs():
    """Load all FAQs from company database to Qdrant"""
    print("=" * 70)
    print("LOADING FAQs FROM COMPANY DATABASE TO QDRANT")
    print("=" * 70)
    print(f"Database: {settings.db_type.upper()} at {settings.db_host}:{settings.db_port}")
    print(f"User: {settings.db_user}")
    if settings.db_type == "oracle":
        print(f"Service: {settings.db_service_name}")
    else:
        print(f"Database: {settings.db_name}")
    print("=" * 70)

    connection = None
    cursor = None
    
    try:
        # Connect to database
        print("\nConnecting to Oracle...")
        dsn = f"{settings.db_host}:{settings.db_port}/{settings.db_service_name}"
        connection = oracledb.connect(
            user=settings.db_user,
            password=settings.db_password,
            dsn=dsn
        )

        # ---------------------------------------------------------
        # FIX FOR LOB ERROR: Auto-convert CLOB to String
        # ---------------------------------------------------------
        def output_type_handler(cursor, name, default_type, size, precision, scale):
            if default_type == oracledb.CLOB:
                return cursor.var(oracledb.STRING, arraysize=cursor.arraysize)
            if default_type == oracledb.BLOB:
                return cursor.var(oracledb.BYTES, arraysize=cursor.arraysize)
                
        connection.outputtypehandler = output_type_handler
        # ---------------------------------------------------------

        cursor = connection.cursor()
        print("✓ Connected successfully")
        
        # Query all active FAQs
        # Adjust schema/table name based on your company database
        query = """
            SELECT 
                CUST_INQ_SEQ as cust_inq_seq,
                LRCL_CD as lrcl_cd,
                MDCL_CD as mdcl_cd,
                SMCL_CD as smcl_cd,
                CUST_QUEST as cust_quest,
                PC_ANS_CONT as pc_ans_cont,
                MC_ANS_CONT as mc_ans_cont,
                RECOMM_GOODS_USE_YN as recomm_goods_use_yn,
                RECOMM_GOODS_AUTO_CRET_YN as recomm_goods_auto_cret_yn,
                DISP_YN as disp_yn,
                QRY_CNT as qry_cnt
            FROM SMRTTSADMIN.CS_CUST_INQ_MGMT_INFO
            WHERE DISP_YN = 'Y'
        """
        
        print("\nQuerying FAQs from database...")
        cursor.execute(query)
        
        # Get column names to create dictionary later
        columns = [col[0].lower() for col in cursor.description]
        rows = cursor.fetchall()
        
        if not rows:
            print("⚠️  No FAQs found in database!")
            print("   Please check:")
            print("   1. Database connection settings")
            print("   2. Table name and schema")
            print("   3. DISP_YN column values")
            return
        
        print(f"✓ Found {len(rows)} FAQs in database")
        
        # Convert rows (tuples) to list of dicts
        faqs = [dict(zip(columns, row)) for row in rows]
        
        # Show sample FAQ
        if faqs:
            sample = faqs[0]
            print("\nSample FAQ:")
            print(f"  ID: {sample['cust_inq_seq']}")
            print(f"  Category: {sample['lrcl_cd']} / {sample.get('mdcl_cd', 'N/A')}")
            print(f"  Question: {sample['cust_quest'][:100]}...")
        
        # Add to Qdrant with OpenAI embeddings
        print(f"\n{'-'*70}")
        print("Adding FAQs to Qdrant with OpenAI embeddings...")
        print(f"Embedding model: {settings.openai_embedding_model}")
        print(f"Embedding dimension: {vector_store.embedding_dim}")
        print(f"{'-'*70}\n")
        
        # We run this in a thread pool because vector_store might be sync or async
        # But vector_store.add_faqs is likely synchronous Qdrant logic
        vector_store.add_faqs(faqs, batch_size=50)
        
        # Verify
        # count = vector_store.get_faq_count()
        # print(f"\n{'='*70}")
        # print(f"✅ SUCCESS: {count} FAQs now in Qdrant")
        # print(f"{'='*70}")
        
        # Test search
        print("\n" + "="*70)
        print("TESTING SEARCH")
        print("="*70)
        
        # test_queries = [
        #     ("배송 기간", None),
        #     ("반품 방법", None),
        #     ("공임비", "C03")  # With category filter
        # ]
        
        # for query, category in test_queries:
        #     print(f"\nQuery: '{query}'")
        #     if category:
        #         print(f"Category filter: {category}")
            
        #     results = vector_store.search_faqs(
        #         query=query,
        #         lrcl_cd=category,
        #         top_k=3
        #     )
            
        #     print(f"Found {len(results)} relevant FAQs:")
        #     for i, faq in enumerate(results, 1):
        #         print(f"\n  {i}. [Score: {faq['similarity_score']:.3f}]")
        #         print(f"     Question: {faq['cust_quest'][:80]}...")
        #         print(f"     Category: {faq['lrcl_cd']} / {faq.get('mdcl_cd', 'N/A')}")
        
        # print("\n" + "="*70)
        # print("✅ LOADING COMPLETE")
        # print("="*70)
        
        # await db_manager.disconnect()
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("\nTroubleshooting:")
        print("1. Check database connection settings in .env")
        print("2. Verify service account has SELECT permissions")
        print("3. Confirm table name and schema")
        print("4. Check OpenAI API key is valid")
    finally:
        # Cleanup
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            print("✓ Database connection closed")

if __name__ == "__main__":
    asyncio.run(load_faqs())
