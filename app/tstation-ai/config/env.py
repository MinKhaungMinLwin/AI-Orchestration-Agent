from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings


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

    ### -------------------------------
    # AI Internal Gateway
    ### -------------------------------
    AI_DEFAULT_PROVIDER: str
    AI_GATEWAY_BASE_URL: str
    AI_GATEWAY_API_KEY: str
    # External AI Providers
    UPSTAGE_API_KEY: str
    OPENAI_API_KEY: str

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


settings = Settings()
