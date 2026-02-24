# isort: skip_file
from fastapi import APIRouter, Depends
from config.env import settings, Environment
from config.sec import get_api_key

## Routers
# Monitoring
from api import monitoring


router = APIRouter()


# Local
if settings.ENV == Environment.LOCAL:
    from api.router_local import router as local_router
    router.include_router(local_router)

# Develop
elif settings.ENV == Environment.DEV:
    # Healthcheck & Metrics
    router.include_router(monitoring.router, tags=["Healthcheck & Metrics"], prefix="")

    # Queue System
    # router.include_router(queue.router, tags=["Queue System"], prefix="/queue", dependencies=[Depends(get_api_key)])


# Staging
elif settings.ENV == Environment.STAGING:
    # Healthcheck & Metrics
    router.include_router(monitoring.router, tags=["Healthcheck & Metrics"], prefix="", include_in_schema=False)
    
    # Queue System
    # router.include_router(queue.router, tags=["Queue System"], prefix="/queue", dependencies=[Depends(get_api_key)])


# Production
elif settings.ENV == Environment.PROD:
    # Healthcheck & Metrics
    router.include_router(monitoring.router, tags=["Healthcheck & Metrics"], prefix="", include_in_schema=False)

else:
    raise Exception("Error Environment with ENV: ", settings.ENV)
