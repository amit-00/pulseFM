import base64
import json

from pulsefm_pubsub.utils import decode_pubsub_push


def test_decode_pubsub_push():
    payload = {"windowId": "w1", "option": "a"}
    body = {
        "message": {
            "data": base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8"),
            "attributes": {"source": "test"},
        }
    }

    decoded, attributes = decode_pubsub_push(body)
    assert decoded == payload
    assert attributes["source"] == "test"
