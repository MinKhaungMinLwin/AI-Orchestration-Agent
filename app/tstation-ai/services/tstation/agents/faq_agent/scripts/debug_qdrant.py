# scripts/debug_qdrant.py
import sys
import os

# Fix path to find modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared import vector_store

def debug_qdrant():
    print("="*50)
    print("🕵️ QDRANT COLLECTION INSPECTOR")
    print("="*50)

    client = vector_store.client
    print("✓ Connected to Qdrant")

    # 1. List ALL Collections
    try:
        response = client.get_collections()
        collections = response.collections
        print(f"\n📚 Found {len(collections)} collections:")
        
        target_collection = None
        max_count = 0

        for col in collections:
            info = client.get_collection(col.name)
            count = info.points_count
            print(f"   - Name: '{col.name}' | Items: {count}")
            
            if count > 0:
                target_collection = col.name
                max_count = count

        if not target_collection:
            print("\n❌ CRITICAL: All collections are empty!")
            return

        print(f"\n✅ Data found in collection: '{target_collection}'")
        
        # 2. Update Settings Recommendation
        from config.settings import settings
        current_setting = settings.qdrant_collection_faq
        
        if current_setting != target_collection:
            print("\n⚠️  CONFIGURATION MISMATCH DETECTED!")
            print(f"   - Your data is in: '{target_collection}'")
            print(f"   - Your settings.py looks for: '{current_setting}'")
            print(f"   Please update 'qdrant_collection_faq' in config/settings.py (or .env) to '{target_collection}'")

    except Exception as e:
        print(f"❌ Error inspecting collections: {e}")

if __name__ == "__main__":
    debug_qdrant()