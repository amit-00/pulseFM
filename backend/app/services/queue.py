import json
from google.cloud import tasks_v2


def enqueue_request(
    project_id: str,
    location: str,
    queue_name: str,
    worker_url: str,
    invoker_sa_email: str,
    payload: dict,
):
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project_id, location, queue_name)

    oidc_token = tasks_v2.OidcToken(
        service_account_email=invoker_sa_email
    )

    http_request = tasks_v2.HttpRequest(
        http_method=tasks_v2.HttpMethod.POST,
        url=worker_url,
        headers={"Content-Type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
        oidc_token=oidc_token,
    )

    task = tasks_v2.Task(http_request=http_request)
    
    task_request = tasks_v2.CreateTaskRequest(parent=parent, task=task)
    response = client.create_task(request=task_request)
    return response.name