from datetime import datetime


def minute_bucket(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


def dedupe_key(window_id: str, session_id: str) -> str:
    return f"vote:{window_id}:{session_id}"


def rate_limit_session_key(session_id: str, bucket: str) -> str:
    return f"rl:s:{session_id}:{bucket}"


def rate_limit_ip_key(ip: str, bucket: str) -> str:
    return f"rl:ip:{ip}:{bucket}"
