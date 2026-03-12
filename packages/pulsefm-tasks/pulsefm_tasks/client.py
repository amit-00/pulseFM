import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from google.api_core import exceptions as gax_exceptions
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2


def _task_client() -> tasks_v2.CloudTasksClient:
    return tasks_v2.CloudTasksClient()


def _task_parent(client: tasks_v2.CloudTasksClient, queue_name: str) -> str:
    project_id = os.getenv("PROJECT_ID", "")
    location = os.getenv("LOCATION", "")
    if not project_id or not location:
        raise ValueError("PROJECT_ID and LOCATION are required")
    return client.queue_path(project_id, location, queue_name)


def _build_json_task(
    client: tasks_v2.CloudTasksClient,
    queue_name: str,
    target_url: str,
    payload: Dict[str, Any],
    task_id: str | None = None,
) -> Dict[str, Any]:
    project_id = os.getenv("PROJECT_ID", "")
    location = os.getenv("LOCATION", "")
    if not project_id or not location:
        raise ValueError("PROJECT_ID and LOCATION are required")

    task: Dict[str, Any] = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload).encode("utf-8"),
        }
    }

    service_account = os.getenv("TASKS_OIDC_SERVICE_ACCOUNT", "")
    if service_account:
        task["http_request"]["oidc_token"] = {"service_account_email": service_account}

    if task_id:
        task["name"] = client.task_path(project_id, location, queue_name, task_id)

    return task


def enqueue_json_task(
    queue_name: str,
    target_url: str,
    payload: Dict[str, Any],
    task_id: str | None = None,
    ignore_already_exists: bool = False,
) -> str | None:
    client = _task_client()
    parent = _task_parent(client, queue_name)
    task = _build_json_task(client, queue_name, target_url, payload, task_id=task_id)

    try:
        response = client.create_task(request={"parent": parent, "task": task})
    except gax_exceptions.AlreadyExists:
        if ignore_already_exists:
            return None
        raise
    return response.name


def enqueue_json_task_with_delay(
    queue_name: str,
    target_url: str,
    payload: Dict[str, Any],
    delay_seconds: float,
    task_id: str | None = None,
    ignore_already_exists: bool = True,
) -> str | None:
    client = _task_client()
    parent = _task_parent(client, queue_name)
    task = _build_json_task(client, queue_name, target_url, payload, task_id=task_id)

    schedule_time = datetime.now(timezone.utc) + timedelta(seconds=max(0.0, float(delay_seconds)))
    timestamp = timestamp_pb2.Timestamp()
    timestamp.FromDatetime(schedule_time)
    task["schedule_time"] = timestamp

    try:
        response = client.create_task(request={"parent": parent, "task": task})
    except gax_exceptions.AlreadyExists:
        if ignore_already_exists:
            return None
        raise
    return response.name
