# agent_flows/faq/flow.py
from typing import Dict, Any, List
from shared import vector_store, llm_client
from config.settings import settings

class FAQAgentFlow:
    """
    Handles FAQ retrieval and answer synthesis (RAG).
    """
    
    async def execute(
        self, 
        question: str, 
        lrcl_cd: str = None, 
        mdcl_cd: str = None, 
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute the FAQ RAG flow
        """
        try:
            # 1. Clean up filters (ensure empty strings become None)
            cat_l = lrcl_cd if lrcl_cd and len(lrcl_cd) > 0 else None
            cat_m = mdcl_cd if mdcl_cd and len(mdcl_cd) > 0 else None
            
            # 2. Search Vector DB
            # Matches the signature in shared/vector_store.py
            faqs = vector_store.search_faqs(
                query=question,
                lrcl_cd=cat_l,
                mdcl_cd=cat_m,
                top_k=3
            )
            
            # 3. Analyze Results
            if not faqs:
                return {
                    "response": "죄송합니다. 질문과 관련된 FAQ를 찾을 수 없습니다. 고객센터(080-022-8272)로 문의해 주세요.",
                    "data": {"faqs_used": 0, "avg_similarity": 0.0}
                }
            
            # Calculate metadata
            scores = [f['similarity_score'] for f in faqs]
            avg_sim = sum(scores) / len(scores) if scores else 0
            
            # 4. Construct Prompt for RAG
            # We take the best match (or top 3) and ask LLM to format it nicely
            context_text = ""
            for i, faq in enumerate(faqs, 1):
                context_text += f"""
                [FAQ #{i}] (Score: {faq['similarity_score']:.2f})
                Q: {faq['cust_quest']}
                A: {faq['pc_ans_cont']}
                """
            
            system_prompt = """
            You are a helpful customer service AI.
            Use the provided FAQ context to answer the user's question.
            
            Guidelines:
            1. Answer specifically based on the Context provided.
            2. If the Context contains the exact answer, summarize it politely in Korean.
            3. Do not make up information not in the context.
            4. Keep the tone polite and professional (honorifics).
            """
            
            user_prompt = f"""
            User Question: {question}
            
            Matched FAQ Context:
            {context_text}
            
            Please provide a helpful answer:
            """
            
            # 5. Generate Answer via LLM
            response_text = llm_client.generate(
                system_prompt=system_prompt,
                prompt=user_prompt,
                temperature=0.3
            )
            
            return {
                "response": response_text,
                "data": {
                    "faqs_used": len(faqs),
                    "avg_similarity": avg_sim,
                    "top_match_id": faqs[0].get('cust_inq_seq')
                }
            }
            
        except Exception as e:
            print(f"❌ FAQ Flow Error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "response": "죄송합니다. FAQ 검색 중 오류가 발생했습니다.",
                "data": {"error": str(e)}
            }