import json
import os
from collections import defaultdict
from urllib.parse import urlparse

import requests
from celery_app import redis
from schemas.queue import QueueRes, TaskStatusEnum


class QueueService(object):
    __instance = None

    @staticmethod
    def get_task(task_id: str) -> QueueRes:
        data = redis.get(task_id)
        if data is None:
            raise ValueError("Can't find task_id")

        data_dict = json.loads(data)
        queue_data = QueueRes(**data_dict)

        # Ascending percent when call
        if queue_data.status == TaskStatusEnum.PROCESSING:
            process_status = queue_data.process_status
            if process_status is None:
                process_status = {
                    "percent": 0,
                    "phase": "Starting...",
                    "message": "",
                }
                queue_data.processing(process_status=process_status)
            else:
                process_status['percent'] += 1
                queue_data.processing(process_status=process_status)

        return queue_data

    @staticmethod
    def delete_task(task_id: str):
        queue_data = QueueService.get_task(task_id)
        # Delete Task
        queue_data.cancelled()

        return queue_data

    @staticmethod
    def get_queue_info(queue_name: str) -> dict:
        """
        Get queue information from queue name in RabbitMQ Management API.


        Response: dict
            messages = messages_ready + messages_unacknowledged
            messages_ready = number messages PENDING
            messages_unacknowledged = number messages PROCESSING
            consumers = number container
            status :
                "running": queue is active and operating normally
                "idle": queue exists but has no ongoing activity
                "flow": queue is under flow control (e.g. throttled due to memory or disk alarms)
        """
        rabbit_url = os.environ.get("RABBITMQ_URL_MANAGEMENT")
        if not rabbit_url:
            raise ValueError("RABBITMQ_URL_MANAGEMENT not found in environment variables.")

        parsed = urlparse(rabbit_url)
        username = parsed.username
        password = parsed.password
        netloc = parsed.hostname
        port = parsed.port or 15672
        base_url = f"http://{netloc}:{port}"


        # URL
        url = f"{base_url}/api/queues/%2F/{queue_name}"

        response = requests.get(url, auth=(username, password))

        if response.status_code == 200:
            data = response.json()
            queue_info = {
                "messages": data.get("messages", 0),
                "messages_ready": data.get("messages_ready", 0),
                "messages_unacknowledged": data.get("messages_unacknowledged", 0),
                "consumers": data.get("consumers", 0),
                "status": data.get("state", "unknown"),
            }
            return queue_info
        else:
            raise Exception(f"Failed to get queue info: {response.status_code} - {response.text}")


    @staticmethod
    def get_count_task(prefixes: list[str]) -> dict:
        result = {}

        for prefix in prefixes:
            status_data = defaultdict(lambda: {"count": 0, "task_ids": []})
            cursor = 0

            while True:
                cursor, keys = redis.scan(cursor=cursor, match=f"{prefix}*", count=100)
                for key in keys:
                    try:
                        value = redis.get(key)
                        if not value:
                            continue
                        obj = QueueRes.model_validate_json(value)
                        status = obj.status.value
                        status_data[status]["count"] += 1
                        status_data[status]["task_ids"].append(obj.task_id)
                    except Exception as e:
                        print(f"Error parsing {key}: {e}")
                if cursor == 0:
                    break

            final_status_data = {
                status.value: status_data.get(status.value, {"count": 0, "task_ids": []})
                for status in TaskStatusEnum
            }
            result[prefix] = final_status_data

        return result
