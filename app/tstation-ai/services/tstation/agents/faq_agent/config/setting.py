# config/settings.py
from pydantic_settings import BaseSettings
from typing import Optional, Literal

class Settings(BaseSettings):
    """Production settings with OpenAI and flexible database support"""
    
    # ==================== OpenAI Configuration ====================
    openai_api_key: str
    openai_model: str = "gpt-4-turbo-preview"
    openai_embedding_model: str = "text-embedding-3-large"
    
    # ==================== Database Configuration ====================
    db_type: Literal["oracle", "postgresql", "mysql"] = "oracle"
    db_host: str
    db_port: int = 1521
    
    # Oracle specific
    db_service_name: Optional[str] = None  # For Oracle
    
    # PostgreSQL/MySQL specific
    db_name: Optional[str] = None  # For PostgreSQL/MySQL
    
    # Credentials
    db_user: str
    db_password: str
    
    # Connection pool
    db_pool_min: int = 2
    db_pool_max: int = 10
    db_pool_increment: int = 1
    
    # ==================== Redis Cache ====================
    redis_url: str = "redis://redis:6379"
    cache_ttl_faq: int = 3600
    cache_ttl_review: int = 1800
    
    # ==================== Qdrant Vector Database ====================
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_api_key: Optional[str] = None
    qdrant_collection_faq: str = "faq_collection"
    qdrant_collection_review: str = "review_collection"

    # redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    # Collections
    faq_collection: str = "faq_collection"
    review_collection: str = "review_collection"
    
    # ==================== Application Settings ====================
    faq_max_results: int = 5
    faq_min_relevance_score: float = 0.7
    review_rag_top_k: int = 5
    review_min_similarity: float = 0.6
    
    # ==================== LLM Settings ====================
    llm_max_tokens: int = 2000
    llm_temperature: float = 0.3
    
    # ==================== Display & Logging ====================
    show_agent_flow_info: bool = True
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    
    # ==================== API Settings ====================
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    api_reload: bool = False
    
    # ==================== Security ====================
    api_key_enabled: bool = False
    api_keys: str = ""  # Comma-separated
    
    # ==================== Monitoring ====================
    enable_metrics: bool = True
    metrics_port: int = 9090
    
    @property
    def database_url(self) -> str:
        """Get database URL based on database type"""
        if self.db_type == "oracle":
            # Oracle connection string
            # Format: oracle+cx_oracle://user:password@host:port/?service_name=SERVICE
            return (
                f"oracle+cx_oracle://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/?service_name={self.db_service_name}"
            )
        elif self.db_type == "postgresql":
            return (
                f"postgresql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        elif self.db_type == "mysql":
            return (
                f"mysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    @property
    def qdrant_url(self) -> str:
        """Get Qdrant URL"""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
    
    @property
    def api_keys_list(self) -> list[str]:
        """Get list of valid API keys"""
        if not self.api_keys:
            return []
        return [key.strip() for key in self.api_keys.split(",") if key.strip()]
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
