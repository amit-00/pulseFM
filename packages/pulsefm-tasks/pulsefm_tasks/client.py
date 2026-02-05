import json
import os
from typing import Any, Dict

from google.cloud import tasks_v2


def enqueue_json_task(queue_name: str, target_url: str, payload: Dict[str, Any]) -> str:
    project_id = os.getenv("PROJECT_ID", "")
    location = os.getenv("LOCATION", "")
    if not project_id or not location:
        raise ValueError("PROJECT_ID and LOCATION are required")

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project_id, location, queue_name)

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

    response = client.create_task(request={"parent": parent, "task": task})
    return response.name
