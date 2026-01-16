import json
import os
from uuid import UUID
from typing import List

from app.models.request import RequestOut


queue_file = f"{os.getcwd()}/queue.json"


def create_queue_file():
    if not os.path.exists(queue_file):
        with open(queue_file, "w") as f:
            f.write("[]")


def get_request_queue():
    if not os.path.exists(queue_file):
        create_queue_file()
        return []

    with open(queue_file, "r") as f:
        return json.load(f)


def save_request_queue(queue: List[RequestOut]):
    if not os.path.exists(queue_file):
        create_queue_file()
            
    with open(queue_file, "w") as f:
        json.dump(queue, f, indent=4)


def add_request_to_queue(request: RequestOut):
    if not os.path.exists(queue_file):
        create_queue_file()

    queue = get_request_queue()
    queue.append(request)
    save_request_queue(queue)


def remove_request_from_queue(request_id: UUID):
    if not os.path.exists(queue_file):
        create_queue_file()
        return []

    queue = get_request_queue()
    queue = [request for request in queue if request["id"] != str(request_id)]
    save_request_queue(queue)