import logging
from dataclasses import dataclass
from typing import Any

from bot.services import TelegramBotService

logger = logging.getLogger("marketplace")


@dataclass(frozen=True)
class TelegramUpdateContext:
    update_id: int | None
    chat_id: int | None
    telegram_user_id: int | None
    username: str
    first_name: str
    message: dict[str, Any] | None
    callback_query: dict[str, Any] | None


@dataclass(frozen=True)
class BotRouteResult:
    handled: bool
    route: str
    chat_id: int | None
    update_id: int | None


def build_update_context(update_data: dict[str, Any]) -> TelegramUpdateContext:
    message = update_data.get("message") or update_data.get("edited_message")
    callback_query = update_data.get("callback_query")

    source_message = message
    if source_message is None and callback_query:
        source_message = callback_query.get("message")

    chat = source_message.get("chat", {}) if source_message else {}
    user = get_update_user(message=message, callback_query=callback_query)

    return TelegramUpdateContext(
        update_id=as_int_or_none(update_data.get("update_id")),
        chat_id=as_int_or_none(chat.get("id")),
        telegram_user_id=as_int_or_none(user.get("id")),
        username=str(user.get("username", "")),
        first_name=str(user.get("first_name", "")),
        message=message,
        callback_query=callback_query,
    )


def get_update_user(
    message: dict[str, Any] | None,
    callback_query: dict[str, Any] | None,
) -> dict[str, Any]:
    if callback_query:
        callback_user = callback_query.get("from")
        if isinstance(callback_user, dict):
            return callback_user

    if message:
        message_user = message.get("from")
        if isinstance(message_user, dict):
            return message_user

    return {}


def as_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_message_text(context: TelegramUpdateContext) -> str:
    if not context.message:
        return ""
    return str(context.message.get("text", "")).strip()


def get_callback_data(context: TelegramUpdateContext) -> str:
    if not context.callback_query:
        return ""
    return str(context.callback_query.get("data", "")).strip()


def get_callback_query_id(context: TelegramUpdateContext) -> str:
    if not context.callback_query:
        return ""
    return str(context.callback_query.get("id", "")).strip()


def log_bot_event(event: str, context: TelegramUpdateContext, **details: Any) -> None:
    detail_text = " ".join(
        f"{key}={value}"
        for key, value in sorted(details.items())
        if value is not None
    )
    logger.info(
        "event=%s update_id=%s chat_id=%s telegram_user_id=%s %s",
        event,
        context.update_id,
        context.chat_id,
        context.telegram_user_id,
        detail_text,
    )


def log_bot_warning(event: str, context: TelegramUpdateContext, **details: Any) -> None:
    detail_text = " ".join(
        f"{key}={value}"
        for key, value in sorted(details.items())
        if value is not None
    )
    logger.warning(
        "event=%s update_id=%s chat_id=%s telegram_user_id=%s %s",
        event,
        context.update_id,
        context.chat_id,
        context.telegram_user_id,
        detail_text,
    )


def acknowledge_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    text: str = "Received",
) -> None:
    callback_query_id = get_callback_query_id(context)
    if callback_query_id:
        bot.answer_callback(callback_query_id, text)


def send_invalid_state_message(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    reason: str,
) -> BotRouteResult:
    log_bot_warning("bot_invalid_state", context, reason=reason)
    if context.chat_id is not None:
        bot.send_text(
            chat_id=context.chat_id,
            text="That action is not available from this screen. Use /start to reopen the menu.",
        )
    return BotRouteResult(
        handled=False,
        route="invalid_state",
        chat_id=context.chat_id,
        update_id=context.update_id,
    )
