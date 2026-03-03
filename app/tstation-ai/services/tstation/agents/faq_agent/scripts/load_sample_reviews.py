# scripts/load_sample_reviews.py
"""
Load sample customer reviews into Qdrant vector store
"""
import sys
sys.path.insert(0, '/app')

from shared import vector_store

SAMPLE_REVIEWS = [
    # Snow performance reviews
    {
        "review_id": "REV_001",
        "product_id": "TIRE_WINTER_001",
        "content": "겨울 타이어로 정말 만족합니다. 눈길에서 제동력이 뛰어나고 미끄러짐이 거의 없어요. 작년 겨울 내내 안전하게 운전했습니다.",
        "rating": 5,
        "metadata": {"season": "winter", "aspect": "snow"}
    },
    {
        "review_id": "REV_002",
        "product_id": "TIRE_WINTER_001",
        "content": "눈 오는 날 고속도로에서 테스트해봤는데 굉장히 안정적이었습니다. 눈길 주행이 걱정되시는 분들께 강력 추천합니다.",
        "rating": 5,
        "metadata": {"season": "winter", "aspect": "snow"}
    },
    {
        "review_id": "REV_003",
        "product_id": "TIRE_ALLSEASON_001",
        "content": "사계절 타이어인데 눈길에서는 아무래도 겨울 타이어보다는 부족합니다. 평지는 괜찮은데 오르막에서 조금 미끄러워요.",
        "rating": 3,
        "metadata": {"season": "all_season", "aspect": "snow"}
    },
    
    # Noise level reviews
    {
        "review_id": "REV_004",
        "product_id": "TIRE_PREMIUM_001",
        "content": "정숙성이 정말 뛰어납니다. 고속도로 주행 시에도 소음이 거의 없어서 장거리 운전이 편해졌어요.",
        "rating": 5,
        "metadata": {"aspect": "noise"}
    },
    {
        "review_id": "REV_005",
        "product_id": "TIRE_PREMIUM_001",
        "content": "이전 타이어 대비 실내 소음이 확실히 줄었습니다. 가격은 좀 비싸지만 조용한 주행을 원하신다면 추천합니다.",
        "rating": 5,
        "metadata": {"aspect": "noise"}
    },
    {
        "review_id": "REV_006",
        "product_id": "TIRE_BUDGET_001",
        "content": "가성비 타이어라 소음은 각오했는데 생각보다 시끄럽네요. 80km 이상에서는 바람 소리가 많이 납니다.",
        "rating": 3,
        "metadata": {"aspect": "noise"}
    },
    
    # Durability reviews
    {
        "review_id": "REV_007",
        "product_id": "TIRE_PREMIUM_001",
        "content": "3년째 사용 중인데 마모가 거의 없습니다. 내구성이 정말 좋아요. 5만 km 주행했는데도 트레드 깊이가 충분합니다.",
        "rating": 5,
        "metadata": {"aspect": "durability"}
    },
    {
        "review_id": "REV_008",
        "product_id": "TIRE_BUDGET_001",
        "content": "1년 반 정도 사용했는데 벌써 마모가 심하네요. 가격이 저렴한 만큼 수명은 짧은 것 같습니다.",
        "rating": 3,
        "metadata": {"aspect": "durability"}
    },
    {
        "review_id": "REV_009",
        "product_id": "TIRE_PREMIUM_001",
        "content": "4만 km 주행 후에도 성능 저하가 없습니다. 초기 구매 비용은 비싸지만 오래 쓸 수 있어서 결국 가성비가 좋네요.",
        "rating": 5,
        "metadata": {"aspect": "durability"}
    },
    
    # Comfort reviews
    {
        "review_id": "REV_010",
        "product_id": "TIRE_COMFORT_001",
        "content": "승차감이 정말 부드럽습니다. 노면 충격을 잘 흡수해서 장거리 운전 시 피로가 덜합니다.",
        "rating": 5,
        "metadata": {"aspect": "comfort"}
    },
    {
        "review_id": "REV_011",
        "product_id": "TIRE_SPORT_001",
        "content": "스포츠 타이어라 승차감은 조금 딱딱한 편이에요. 코너링 성능은 좋지만 편안함을 원하시면 비추천합니다.",
        "rating": 3,
        "metadata": {"aspect": "comfort"}
    },
    
    # Rain performance reviews
    {
        "review_id": "REV_012",
        "product_id": "TIRE_PREMIUM_001",
        "content": "빗길 제동력이 우수합니다. 폭우에도 수막 현상 없이 안정적으로 주행할 수 있었어요.",
        "rating": 5,
        "metadata": {"aspect": "rain"}
    },
    {
        "review_id": "REV_013",
        "product_id": "TIRE_PREMIUM_001",
        "content": "비 오는 날 고속도로에서도 미끄러짐 없이 안전했습니다. 배수 성능이 정말 뛰어나네요.",
        "rating": 5,
        "metadata": {"aspect": "rain"}
    },
    
    # Overall satisfaction reviews
    {
        "review_id": "REV_014",
        "product_id": "TIRE_PREMIUM_001",
        "content": "전반적으로 모든 면에서 만족스럽습니다. 가격 대비 성능, 내구성, 정숙성 모두 훌륭해요. 다음에도 재구매 의향 있습니다.",
        "rating": 5,
        "metadata": {"aspect": "overall"}
    },
    {
        "review_id": "REV_015",
        "product_id": "TIRE_BUDGET_001",
        "content": "가격이 저렴한 만큼 성능은 평범합니다. 도심 주행용으로는 괜찮지만 고속 주행이나 눈길은 비추천합니다.",
        "rating": 3,
        "metadata": {"aspect": "overall"}
    },
]

def main():
    """Load sample reviews into Qdrant"""
    print("=" * 60)
    print("Loading sample reviews to Qdrant...")
    print("=" * 60)
    
    try:
        # Check current count
        current_count = vector_store.get_review_count()
        print(f"Current review count: {current_count}")
        
        # Add reviews
        print(f"Adding {len(SAMPLE_REVIEWS)} sample reviews...")
        vector_store.add_reviews(SAMPLE_REVIEWS, batch_size=50)
        
        # Verify
        new_count = vector_store.get_review_count()
        print(f"New review count: {new_count}")
        print(f"✅ Successfully added {new_count - current_count} reviews")
        
        # Test search
        print("\n--- Testing search ---")
        results = vector_store.search_reviews(
            query="눈길에서 어때요?",
            top_k=3
        )
        
        print(f"Found {len(results)} relevant reviews:")
        for i, review in enumerate(results, 1):
            print(f"\n{i}. Similarity: {review['similarity_score']:.3f}")
            print(f"   Content: {review['content'][:100]}...")
            print(f"   Rating: {review.get('rating')}/5")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
