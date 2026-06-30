import json
import logging
from json import JSONDecodeError
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .dispatcher import dispatch_telegram_update

logger = logging.getLogger("marketplace")


@csrf_exempt
@require_POST
def telegram_webhook(request: HttpRequest) -> JsonResponse:
    expected_secret = settings.BOT_WEBHOOK_SECRET
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    if not expected_secret:
        logger.error("event=telegram_webhook_secret_missing path=%s", request.path)
        return JsonResponse(
            {
                "success": False,
                "error": "Webhook secret is not configured",
            },
            status=500,
        )

    if received_secret != expected_secret:
        logger.warning(
            "event=telegram_webhook_rejected_invalid_secret path=%s",
            request.path,
        )
        return JsonResponse(
            {
                "success": False,
                "error": "Unauthorized",
            },
            status=401,
        )

    try:
        update_data = decode_json_body(request)
    except UnicodeDecodeError as exc:
        logger.warning(
            "event=telegram_webhook_rejected_bad_encoding path=%s error=%s",
            request.path,
            exc,
        )
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request encoding",
            },
            status=400,
        )
    except JSONDecodeError as exc:
        logger.warning(
            "event=telegram_webhook_rejected_invalid_json path=%s error=%s",
            request.path,
            exc,
        )
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid JSON",
            },
            status=400,
        )

    try:
        route_result = dispatch_telegram_update(update_data)
    except Exception as exc:
        logger.exception(
            "event=telegram_webhook_handling_failed path=%s error=%s",
            request.path,
            exc,
        )
        return JsonResponse(
            {
                "success": False,
                "error": "Webhook handling failed",
            },
            status=500,
        )

    logger.info(
        "event=telegram_webhook_handled update_id=%s chat_id=%s route=%s handled=%s",
        route_result.update_id,
        route_result.chat_id,
        route_result.route,
        route_result.handled,
    )

    return JsonResponse(
        {
            "success": True,
            "handled": route_result.handled,
            "route": route_result.route,
        }
    )


def decode_json_body(request: HttpRequest) -> dict[str, Any]:
    decoded_body = request.body.decode("utf-8")
    payload = json.loads(decoded_body)

    if not isinstance(payload, dict):
        raise JSONDecodeError("Telegram update payload must be a JSON object.", decoded_body, 0)

    return payload
