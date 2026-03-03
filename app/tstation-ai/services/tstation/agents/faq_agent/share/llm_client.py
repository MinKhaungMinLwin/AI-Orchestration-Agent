# shared/llm_client.py
from openai import OpenAI
from config.settings import settings
from typing import List, Optional, Any
import time

class OpenAIClient:
    """
    OpenAI API client wrapper for LLM and Embeddings
    Synchronous implementation to match vector_store requirements.
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.embedding_model = settings.openai_embedding_model
        self.max_tokens = 1000 
        self.temperature = 0.0
        
        # Get embedding dimensions
        if "small" in self.embedding_model:
            self.embedding_dim = 1536
        else:
            self.embedding_dim = 3072

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate text using OpenAI chat completion"""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature if temperature is not None else self.temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"❌ OpenAI API error: {e}")
            return "I apologize, but I encountered an error generating a response."
    
    def embed(self, text: str, retry_count: int = 3) -> List[float]:
        """Generate single embedding"""
        text = text.replace("\n", " ")
        for attempt in range(retry_count):
            try:
                response = self.client.embeddings.create(
                    model=self.embedding_model,
                    input=text
                )
                return response.data[0].embedding
            except Exception as e:
                if attempt < retry_count - 1:
                    time.sleep(1)
                else:
                    print(f"❌ OpenAI Embeddings error: {e}")
                    return [0.0] * self.embedding_dim
    
    def embed_batch(
        self, 
        texts: List[str], 
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.
        Crucial: Handles the 'batch_size' argument required by vector_store.py
        """
        all_embeddings = []
        
        # Process in chunks
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            
            # Sanitize inputs
            batch = [t.replace("\n", " ") for t in batch]
            
            try:
                response = self.client.embeddings.create(
                    model=self.embedding_model,
                    input=batch
                )
                # Extract embeddings
                batch_embeddings = [data.embedding for data in response.data]
                all_embeddings.extend(batch_embeddings)
                
            except Exception as e:
                print(f"❌ Batch embedding error: {e}")
                # Fallback: add zero vectors to keep indices aligned
                zero_vector = [0.0] * self.embedding_dim
                all_embeddings.extend([zero_vector] * len(batch))
        
        return all_embeddings

# Create the global instance
llm_client = OpenAIClient()