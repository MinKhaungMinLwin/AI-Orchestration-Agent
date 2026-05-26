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

    ### -------------------------------
    # RAG (Retrieval-Augmented Generation)
    ### -------------------------------
    # Qdrant Vector Store
    QDRANT_HOST: str = Field(default="localhost")
    QDRANT_PORT: int = Field(default=6333)
    QDRANT_API_KEY: str = Field(default="")
    QDRANT_COLLECTION_FAQ: str = Field(
        default="",
        description="Qdrant collection name for FAQ documents",
    )
    # Embedding
    EMBEDDING_PROVIDER: str = Field(default="openai")
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-large")

    ### -------------------------------
    # FAQ Periodic Sync (tstation-be → Qdrant)
    ### -------------------------------
    TSTATION_BE_API: str = Field(
        default="",
        description="Base URL for tstation-be API (e.g. http://tstation-be:8000). Required for periodic FAQ sync.",
    )
    JWT_TOKEN: str = Field(
        default="",
        description="Bearer JWT token used by the ingestion service to authenticate against tstation-be /api/faq.",
    )
    FAQ_SYNC_INTERVAL_SECONDS: int = Field(
        default=25200,
        description="Interval in seconds between periodic FAQ fetches from tstation-be into Qdrant.",
    )

    class Config:
        # automatically load variables from a .env file in the project root
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # ignore any additional vars like NGINX_PORT, AWS_BEARER_TOKEN_BEDROCK


settings = Settings()
