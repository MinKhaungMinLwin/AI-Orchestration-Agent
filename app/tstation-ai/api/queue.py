import time

from fastapi import APIRouter, HTTPException
from schemas.queue import QueueRes, TaskStatusEnum
from services.queue import QueueService

router = APIRouter()

@router.get("/{task_id}")
def get_task(*, task_id: str) -> QueueRes:
    """
    Get task from Queue System

    Parameters:

        task_id (str): Task ID

    Returns:

        status (str): ['NEW', 'PENDING', 'PROCESSING', 'SUCCESS', 'FAILURE', 'CANCELLED', 'KILL']
        process_status (dict): Show [percent, phase, message] of current task status when 'PROCESSING'
        result (dict):
            - status_code (int): Status code
            - data (Any): data when task 'SUCCESS'
            - error (Any): error when task 'FAILURE' | 'KILL'

    """
    try:
        queue_data = QueueService.get_task(task_id)

        # Handler status of task
        queue_data.metadata.queue_info = QueueService.get_queue_info(queue_name=queue_data.metadata.queue_name)

        # Delete task when timeout (8 hours)
        if queue_data.status in [TaskStatusEnum.PENDING, TaskStatusEnum.PROCESSING]:
            current_time = int(time.time())
            total_time = current_time - queue_data.metadata.time.start
            if total_time > 8*3600:
                queue_data.kill(detail="Task timeout")

        return queue_data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{task_id}")
def delete_task(*, task_id: str) -> QueueRes:
    try:
        queue_data = QueueService.delete_task(task_id)
        return queue_data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/count/task")
def get_count_task():
    """
    Get count status of task in Queue System
    """
    try:
        # Import func running in queue system to monitor
        from api.gene.index import index_queue

        PREFIX = [
            str(index_queue.__name__)
        ]

        response = QueueService.get_count_task(PREFIX)
        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

