# isort: skip_file
from fastapi import APIRouter

# Routers
from api import monitoring


router = APIRouter()

# Healthcheck & Metrics
router.include_router(monitoring.router, tags=["Healthcheck & Metrics"], prefix="")

# # Queue System
# router.include_router(queue.router, tags=["Queue System"], prefix="/queue")

