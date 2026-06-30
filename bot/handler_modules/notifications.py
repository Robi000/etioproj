from bot.services import TelegramBotService

from .utils import (
    BotRouteResult,
    TelegramUpdateContext,
    acknowledge_callback,
    log_bot_event,
)


NOTIFICATIONS_CALLBACK = "notifications:open"
NOTIFICATION_COMMANDS = {"/notifications", "/notices"}


def can_handle_callback(callback_data: str) -> bool:
    return callback_data == NOTIFICATIONS_CALLBACK


def can_handle_text(text: str) -> bool:
    command = text.split(maxsplit=1)[0].lower() if text else ""
    return command in NOTIFICATION_COMMANDS


def handle_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    callback_data: str,
) -> BotRouteResult:
    acknowledge_callback(bot, context)
    log_bot_event("bot_callback_notifications", context, callback_data=callback_data)
    return send_notification_center(bot, context, route="notifications.callback")


def handle_notifications_command(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    text: str,
) -> BotRouteResult:
    command = text.split(maxsplit=1)[0].lower() if text else "/notifications"
    log_bot_event("bot_command_notifications", context, command=command)
    return send_notification_center(bot, context, route="notifications.command")


def send_notification_center(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    route: str,
) -> BotRouteResult:
    if context.chat_id is not None:
        bot.send_text(
            chat_id=context.chat_id,
            text="No notifications are waiting in this chat right now.",
            reply_markup=bot.build_mini_app_keyboard("Open Marketplace"),
        )

    return BotRouteResult(
        handled=True,
        route=route,
        chat_id=context.chat_id,
        update_id=context.update_id,
    )
