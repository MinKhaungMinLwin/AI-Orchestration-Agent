from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    ### -------------------------------
    # Application
    ### -------------------------------
    
    PROJECT_NAME: str
    ENV: Environment = Field(
        default=Environment.DEV,
        description="Environment name, one of: [local, dev, staging, prod]",
    )
    LOG_LEVEL: LogLevel = Field(
        default=LogLevel.INFO,
        description="Log level, one of: ['DEBUG', 'INFO', 'WARNING', 'ERROR']",
    )
    APP_PORT: int = 8000
    ROOT_PATH: str
    APP_STATIC_DIR: str = "static"
    APP_PUBLIC_DIR: str = "static/public"
    API_SECRET_KEY: str
    TZ_OFFSET: int = 7

    # TSTATION-BE
    TSTATION_BE_API: str
    TSTATION_BE_MCP: str
    ### -------------------------------
    # AI Internal Gateway
    ### -------------------------------
    AI_DEFAULT_PROVIDER: str
    AI_GATEWAY_BASE_URL: str
    AI_GATEWAY_API_KEY: str
    AI_MODEL: str
    AI_QC_MODEL: str
    # External AI Providers
    UPSTAGE_API_KEY: str
    OPENAI_API_KEY: str

    # Redis Conversation Management
    REDIS_CONVERSATION_MANAGEMENT_PASSWORD: str
    REDIS_CONVERSATION_MANAGEMENT_URL: str


### -------------------------------
    # Queue System
    ### -------------------------------
    # Redis
    REDIS_PASSWORD: str
    REDIS_URL: str
    # RabbitMQ
    RABBITMQ_NODENAME: str
    RABBITMQ_USERNAME: str
    RABBITMQ_PASSWORD: str
    RABBITMQ_TM_PORT: int = 15672
    RABBITMQ_URL: str
    RABBITMQ_URL_MANAGEMENT: str
    # Worker
    NUM_WORKER: int = 2

    ### -------------------------------
    # AWS
    ### -------------------------------
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_DEFAULT_REGION: str
    S3_BUCKET_NAME: str

    ### -------------------------------
    # Monitoring & Tracing
    ### -------------------------------
    GF_SECURITY_ADMIN_USER: str
    GF_SECURITY_ADMIN_PASSWORD: str
    LOKI_URL: str
    PROMETHEUS_URL: str
    LANGFUSE_HOST: str
    LANGFUSE_PROJECT_NAME: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_PUBLIC_KEY: str

    ### -------------------------------
    # RAG (Retrieval-Augmented Generation)
    ### -------------------------------
    # Qdrant Vector Store
    QDRANT_HOST: str = Field(default="localhost")
    QDRANT_PORT: int = Field(default=6333)
    QDRANT_API_KEY: str = Field(default="")
    QDRANT_COLLECTION_FAQ: str = Field(
        default="hankook_faq_docs",
        description="Qdrant collection name for FAQ documents",
    )
    # Embedding
    EMBEDDING_PROVIDER: str = Field(default="openai")
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small")
    # Chunking
    RAG_CHUNK_SIZE: int = Field(default=512)
    RAG_CHUNK_OVERLAP: int = Field(default=50)
    # Search
    RAG_SEARCH_TOP_K: int = Field(default=5)
    RAG_SEARCH_SCORE_THRESHOLD: float = Field(default=0.7)

    class Config:
        # automatically load variables from a .env file in the project root
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # ignore any additional vars like NGINX_PORT, AWS_BEARER_TOKEN_BEDROCK


settings = Settings()
