# isort: skip_file
from fastapi import APIRouter
from config.env import settings, Environment

## Routers
# Monitoring
from api import monitoring

# T-station
from api.tstation import chat_message as tstation_chat_message

router = APIRouter()


# Local
if settings.ENV == Environment.LOCAL:
    from api.router_local import router as local_router
    router.include_router(local_router)

# Develop
elif settings.ENV == Environment.DEV:
    # Healthcheck & Metrics
    router.include_router(monitoring.router, tags=["Healthcheck & Metrics"], prefix="")

    # T-Station Chat
    router.include_router(tstation_chat_message.router, tags=["Chat Message"], prefix="/tstation/messages")



# Staging
elif settings.ENV == Environment.STAGING:
    # Healthcheck & Metrics
    router.include_router(monitoring.router, tags=["Healthcheck & Metrics"], prefix="", include_in_schema=False)

    # T-Station Chat
    router.include_router(tstation_chat_message.router, tags=["Chat Message"], prefix="/tstation/messages")


# Production
elif settings.ENV == Environment.PROD:
    # Healthcheck & Metrics
    router.include_router(monitoring.router, tags=["Healthcheck & Metrics"], prefix="", include_in_schema=False)

else:
    raise Exception("Error Environment with ENV: ", settings.ENV)
