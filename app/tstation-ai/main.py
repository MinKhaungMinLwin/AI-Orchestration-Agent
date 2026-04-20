import logging
import os
from contextlib import asynccontextmanager

from api.router import router
from config.env import settings
from config.log import setup_logging
from config.tracing import tracer
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Setup Logging
setup_logging(
    service_name=settings.PROJECT_NAME,
    ignored_paths=["/metrics", "/health"]
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tracer is already initialised at import time; flush on shutdown.
    yield
    tracer.flush()


app = FastAPI(
    root_path=settings.ROOT_PATH,
    title=f"{settings.PROJECT_NAME.upper()} APIs {settings.ENV.value.upper()}",
    description="APIs Swagger Documentation",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Public dir
os.makedirs(settings.APP_PUBLIC_DIR, exist_ok=True)
app.mount("/public", StaticFiles(directory=settings.APP_PUBLIC_DIR), name="public")


if __name__ == "__main__":
    import uvicorn
    env = settings.ENV
    logger.info(f"Starting app with ENVIRONMENT: {env.value}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=(env == "local")
    )
