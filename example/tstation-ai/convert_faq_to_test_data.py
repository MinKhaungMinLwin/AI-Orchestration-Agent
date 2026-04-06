#!/usr/bin/env python3
"""
Convert FAQ API response to test data format for RAG indexing.

Usage:
    1. Get FAQ response from API and save as faq_api_response.json
    2. Run: python convert_faq_to_test_data.py
    3. It will create faq_test_data.json
"""

import json
from pathlib import Path


def convert_api_response_to_test_format(api_response: dict) -> list[dict]:
    """
    Convert FAQ API response to test data format.
    
    API Format:
        {
            "total": 165,
            "items": [
                {
                    "lrcl_cd": "C01",
                    "mdcl_cd": "C0103",
                    "cust_quest": "Question text",
                    "pc_ans_cont": "Answer content"
                },
                ...
            ]
        }
    
    Test Format:
        [
            {
                "id": 1,
                "content": "Question: ... Answer: ..."
            },
            ...
        ]
    """
    test_data = []
    
    items = api_response.get("items", [])
    for idx, item in enumerate(items, start=1):
        question = item.get("cust_quest", "").strip()
        answer = item.get("pc_ans_cont", "").strip()
        category = f"{item.get('lrcl_cd', 'N/A')}-{item.get('mdcl_cd', 'N/A')}"
        
        # Combine question + answer + category for better semantic search
        # Strip HTML tags
        answer_clean = answer.replace("<br />", " ").replace("<br/>", " ")
        answer_clean = answer_clean.replace("<font color=\"blue\">", "").replace("</font>", "")
        answer_clean = answer_clean.replace("▶", "").replace("&nbsp;", " ")
        answer_clean = answer_clean.strip()
        
        # Create content: question + answer
        content = f"Q: {question}\nA: {answer_clean}\nCategory: {category}"
        
        test_data.append({
            "id": idx,
            "cust_quest": question,
            "pc_ans_cont": answer_clean,
            "category": category,
            "content": content,  # Combined for indexing
        })
    
    return test_data


def main():
    # Path to API response file
    api_response_file = Path(__file__).parent / "faq_api_response.json"
    output_file = Path(__file__).parent / "faq_test_data.json"
    
    if not api_response_file.exists():
        print(f"❌ File not found: {api_response_file}")
        print(f"📝 Please create {api_response_file} with FAQ API response")
        print(f"""
Example format:
{{
    "total": 165,
    "items": [
        {{
            "lrcl_cd": "C01",
            "mdcl_cd": "C0103",
            "cust_quest": "회원가입은 어떻게 하나요?",
            "pc_ans_cont": "티스테이션닷컴 [회원가입] 메뉴를 통해..."
        }},
        ...
    ]
}}
        """)
        return
    
    # Load API response
    with open(api_response_file, "r", encoding="utf-8") as f:
        api_response = json.load(f)
    
    print(f"📖 Loaded {len(api_response.get('items', []))} FAQs from API response")
    
    # Convert to test format
    test_data = convert_api_response_to_test_format(api_response)
    
    # Save as test data (using only id + content for RAG indexing)
    test_data_for_indexing = [
        {"id": item["id"], "content": item["content"]}
        for item in test_data
    ]
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(test_data_for_indexing, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Converted {len(test_data)} FAQs")
    print(f"✅ Saved to: {output_file}")
    print(f"\n📊 Sample (first 2 FAQs):")
    for item in test_data[:2]:
        print(f"\n  ID: {item['id']}")
        print(f"  Q: {item['cust_quest'][:80]}...")
        print(f"  A: {item['pc_ans_cont'][:100]}...")
        print(f"  Category: {item['category']}")


if __name__ == "__main__":
    main()
