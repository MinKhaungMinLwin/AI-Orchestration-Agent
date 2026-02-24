import logging

from config.env import Environment, settings
from langfuse import Langfuse

logger = logging.getLogger(__name__)

# Config
tracer = Langfuse(
    host=settings.LANGFUSE_HOST,
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    # Environment
    environment=settings.ENV,
    # Debug
    debug=True if settings.ENV == Environment.LOCAL else False,
)
tracer.auth_check()

logger.info(f"Enabled tracing with project '{settings.LANGFUSE_PROJECT_NAME}', environment '{settings.ENV}'")
