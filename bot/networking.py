import socket
from typing import Any

from urllib3.util import connection as urllib3_connection


def force_requests_ipv4() -> None:
    urllib3_connection.allowed_gai_family = lambda: socket.AF_INET


def redact_telegram_token(value: Any, token: str) -> str:
    text = str(value)
    if not token:
        return text

    return text.replace(token, "<telegram-bot-token>")
