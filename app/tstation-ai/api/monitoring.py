import logging
import socket

from config.sec import get_api_key
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from services.queue import QueueService

logger = logging.getLogger(__name__)
router = APIRouter()


# Healthcheck endpoint
@router.get("/health", summary="Service health check")
async def healthcheck():
    """
    Healthcheck endpoint.
    """
    return {
        "status": "ok",
        "hostname": socket.gethostname()
    }

@router.get("/test/success", dependencies=[Depends(get_api_key)])
async def return_success():
    """
    Success endpoint for testing purposes.
    """
    logger.info("At /test/success: This is a test success")
    return {"message": "Test Success"}


class ErrorRequest(BaseModel):
    error_code: int = 500
    error_message: str = "Example error message"


@router.post("/test/raise-error", dependencies=[Depends(get_api_key)])
async def raise_error(request: ErrorRequest):
    """
    Error endpoint for testing purposes.
    """
    logger.error("At /test/raise-error: This is a test error with code %s: %s", request.error_code, request.error_message)
    raise HTTPException(
        status_code=request.error_code,
        detail=request.error_message
    )


# Metrics endpoint
@router.get(
    "/metrics",
    dependencies=[Depends(get_api_key)]
)
def prometheus_metrics():
    """
    API metrics in Prometheus format
    """

    try:
        lines = []
        # Healthcheck
        lines.extend(["healthcheck 1"])

        # Count queue task status
        # lines.extend(queue_task_count())

        return Response(content="\n".join(lines) + "\n", media_type="text/plain")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def queue_task_count() -> list[str]:
    # Import func running in queue system to monitor
    from api.gene.index import index_queue

    PREFIX = [
        str(index_queue.__name__),
    ]

    result = QueueService.get_count_task(PREFIX)
    lines = []
    for prefix, status_map in result.items():
        for status, data in status_map.items():
            metric_name = "queue_task_count"
            labels = f'queue_name="{prefix}",status="{status}"'
            line = f'{metric_name}{{{labels}}} {data["count"]}'
            lines.append(line)

    return lines
