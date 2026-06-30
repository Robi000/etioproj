import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings
from django.db import close_old_connections

from bot.handler_modules.utils import BotRouteResult, build_update_context
from bot.handlers import handle_telegram_update

logger = logging.getLogger("marketplace")

_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="telegram-bot",
)


def dispatch_telegram_update(update_data: dict[str, Any]) -> BotRouteResult:
    if not settings.BOT_WEBHOOK_ASYNC:
        return handle_telegram_update(update_data)

    context = build_update_context(update_data)
    _executor.submit(handle_telegram_update_safely, update_data)

    logger.info(
        "event=telegram_webhook_update_queued update_id=%s chat_id=%s",
        context.update_id,
        context.chat_id,
    )

    return BotRouteResult(
        handled=True,
        route="webhook.queued",
        chat_id=context.chat_id,
        update_id=context.update_id,
    )


def handle_telegram_update_safely(update_data: dict[str, Any]) -> None:
    close_old_connections()
    try:
        route_result = handle_telegram_update(update_data)
        logger.info(
            "event=telegram_webhook_background_handled update_id=%s chat_id=%s route=%s handled=%s",
            route_result.update_id,
            route_result.chat_id,
            route_result.route,
            route_result.handled,
        )
    except Exception as exc:
        context = build_update_context(update_data)
        logger.exception(
            "event=telegram_webhook_background_failed update_id=%s chat_id=%s error=%s",
            context.update_id,
            context.chat_id,
            exc,
        )
    finally:
        close_old_connections()
