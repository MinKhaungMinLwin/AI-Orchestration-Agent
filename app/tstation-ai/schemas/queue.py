import time
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from celery_app import redis
from pydantic import BaseModel, Field, model_validator


class TaskStatusEnum(str, Enum):
    NEW = "NEW"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"
    KILL = "KILL"

# Metadata
class TimeMetadata(BaseModel):
    start: int = Field(default_factory=lambda: int(time.time()), description="Unix timestamp when task started")
    end: Optional[int] = Field(None, description="Unix timestamp when task ended")
    total: Optional[int] = Field(None, description="Total seconds taken by the task")

    @model_validator(mode="after")
    def calculate_total(self) -> "TimeMetadata":
        if self.start is not None and self.end is not None:
            self.total = self.end - self.start
        return self

    def end_now(self) -> "TimeMetadata":
        self.end = int(time.time())
        return self

class Metadata(BaseModel):
    queue_name: str = Field(..., description="Queue name in celery")
    task_name: str = Field(..., description="Task name")
    time: Optional[TimeMetadata] = None
    queue_info: Optional[Any] = None
    logs_task: Any = None

    model_config = {
        "extra": "allow"
    }

class QueueResult(BaseModel):
    status_code: int = Field(..., description="Status of task with HTTP status code")
    data: Any = Field(None, description="Task result data if success")
    error: Any = Field(None, description="Error details if failed")

# Queue Response
class QueueRes(BaseModel):
    task_id: str = Field(..., description="Task unique ID")
    status: TaskStatusEnum = Field(..., description="Task status")
    process_status: Optional[Dict[str, Any]] = Field(None, description="Task progress info")
    result: Optional[QueueResult] = Field(None, description="Task result")
    metadata: Optional[Metadata] = Field(None, description="Extra task metadata")

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": "task_name_uuid_str",
                "status": "NEW",
                "process_status": None,
                "result": {
                    "status_code": 200,
                    "data": {},
                    "error": {"message": "Internal Server Error", "detail": "Max retries, File is large"}
                },
                "metadata": {
                    "queue_name": "queue_name",
                    "task_name": "task_name",
                    "time": {
                        "start": 1688997600,
                        "end": 1688997650,
                        "total": 50
                    },
                    "queue_info": None,
                    "logs_task": None,
                    "add_key_here": "add_value_here"
                },
            }
        }
    }

    def _add_pipeline_log(self, process_status: Any = None):
        """
        Add current status to logs_task["pipeline"]
        """
        log_item = {
            "status": self.status,
            "timestamp": int(time.time())
        }

        if process_status:
            log_item['process_status'] = process_status

        if self.metadata.logs_task is None:
            self.metadata.logs_task = {}
        if "pipeline" not in self.metadata.logs_task:
            self.metadata.logs_task["pipeline"] = []

        self.metadata.logs_task["pipeline"].append(log_item)


    @classmethod
    def new(cls, queue_name: str, task_name: str) -> 'QueueRes':
        """
        Create task with status is: NEW
            - Create task_id
            - save start timestamp
        """
        task_id = f"{task_name}_{uuid4()}".replace("-", "_")
        metadata = Metadata(
            queue_name=queue_name,
            task_name=task_name,
            time=TimeMetadata(),
        )

        response = QueueRes(
            task_id=task_id,
            status=TaskStatusEnum.NEW,
            metadata=metadata,
        )
        # Save to storage
        response._add_pipeline_log()
        redis.set(response.task_id, response.model_dump_json())
        return response

    def pending(self):
        """
        Change task status: NEW -> PENDING
        """
        if self.status == TaskStatusEnum.NEW:
            self.status = TaskStatusEnum.PENDING
            self._add_pipeline_log()
            redis.set(self.task_id, self.model_dump_json())


    def processing(self, process_status: dict = None):
        """
        Change task status: PENDING|PROCESSING -> PROCESSING
        at PROCESSING, can update dictionary: process_status
        """
        self.status = TaskStatusEnum.PROCESSING
        self.process_status = process_status
        self._add_pipeline_log(process_status)
        redis.set(self.task_id, self.model_dump_json())

    def success(self, data: Any):
        """
        Change task status: PROCESSING -> SUCCESS
        Return result

        """
        self.status = TaskStatusEnum.SUCCESS
        self.result = QueueResult(
            status_code=200,
            data=data,
            error=None,
        )
        self.metadata.time.end = int(time.time())
        self._add_pipeline_log()
        redis.set(self.task_id, self.model_dump_json())

    def cancelled(self):
        """
        Change task status: -> CANCELLED (exception PROCESSING)
        """
        if self.status is not TaskStatusEnum.PROCESSING:
            self.status = TaskStatusEnum.CANCELLED
            self.result = QueueResult(
                status_code=499,
                data=None,
                error={"message": "Task cancelled"},
            )
            self.metadata.time.end = int(time.time())
            self._add_pipeline_log()
            redis.set(self.task_id, self.model_dump_json())
        else:
            raise ValueError("Can't stop task when processing")


    def failure(self, status_code: int, message: str):
        """
        Change task status: -> FAILURE
        Return error
        """
        self.status = TaskStatusEnum.FAILURE
        self.result = QueueResult(
            status_code=status_code,
            data=None,
            error={"message": message},
        )
        self.metadata.time.end = int(time.time())
        self._add_pipeline_log()
        redis.set(self.task_id, self.model_dump_json())


    def kill(self, detail: str):
        """
        Change task status: KILL
        """
        self.status = TaskStatusEnum.KILL
        self.result = QueueResult(
            status_code=500,
            data=None,
            error={
                "message": "Internal Server Error",
                "detail": detail
            },
        )
        self.metadata.time.end = int(time.time())
        self._add_pipeline_log()
        redis.set(self.task_id, self.model_dump_json())
