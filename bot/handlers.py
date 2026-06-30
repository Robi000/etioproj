import logging
from typing import Any

from bot.handler_modules import (
    admin,
    contact_requests,
    discovery,
    notifications,
    policy,
    registration,
    start,
    survey,
)
from bot.handler_modules.utils import (
    BotRouteResult,
    TelegramUpdateContext,
    acknowledge_callback,
    build_update_context,
    get_callback_data,
    get_message_text,
    log_bot_event,
    log_bot_warning,
    send_invalid_state_message,
)
from bot.services import TelegramBotService

logger = logging.getLogger("marketplace")


def handle_telegram_update(update_data: dict[str, Any]) -> BotRouteResult:
    context = build_update_context(update_data)

    if context.telegram_user_id is not None:
        from accounts.models import TelegramUser
        user = TelegramUser.objects.filter(telegram_id=context.telegram_user_id).first()
        if user is not None:
            user.update_last_interaction(save=True)

    if context.chat_id is None:
        log_bot_warning("bot_update_missing_chat", context)
        return BotRouteResult(
            handled=False,
            route="update.missing_chat",
            chat_id=None,
            update_id=context.update_id,
        )

    bot = TelegramBotService()

    if context.callback_query:
        result = dispatch_callback_query(bot, context)
        callback_data = get_callback_data(context)
        contact_requests.send_pending_alert_if_needed(bot, context, callback_data)
        return result

    if context.message:
        result = dispatch_message(bot, context)
        contact_requests.send_pending_alert_if_needed(bot, context)
        return result

    return send_invalid_state_message(
        bot=bot,
        context=context,
        reason="unsupported_update_type",
    )


def dispatch_message(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
) -> BotRouteResult:
    message = context.message or {}
    text = get_message_text(context) if "text" in message else ""

    if "text" not in message and policy.needs_policy_gate(context):
        return policy.start_policy_flow(bot, context, "policy.gate.message")

    if registration.should_force_offline_message(
        context.telegram_user_id,
        text=text,
    ):
        return registration.send_offline_warning(bot, context)

    if "text" in message:
        return dispatch_text_message(
            bot=bot,
            context=context,
            text=text,
        )

    if "contact" in message:
        return registration.handle_contact_message(bot, context)

    if "location" in message:
        return registration.handle_location_message(bot, context)

    if "photo" in message:
        return registration.handle_photo_message(bot, context)

    return send_invalid_state_message(
        bot=bot,
        context=context,
        reason="unsupported_message_type",
    )


def dispatch_text_message(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    text: str,
) -> BotRouteResult:
    log_bot_event("bot_text_received", context, text=text[:80])

    if policy.needs_policy_gate(context):
        return policy.start_policy_flow(bot, context, "policy.gate.text")

    if start.can_handle_text(text):
        return start.handle_start_command(bot, context, text)

    if admin.can_handle_text(text):
        return admin.handle_admin_command(bot, context, text)

    if notifications.can_handle_text(text):
        return notifications.handle_notifications_command(bot, context, text)

    if discovery.can_handle_text(text):
        return discovery.handle_discovery_command(bot, context, text)

    if registration.can_handle_text(text) or registration.has_active_session(
        context.telegram_user_id
    ):
        return registration.handle_text(bot, context, text)

    return discovery.handle_fallback_text(bot, context, text)


def dispatch_callback_query(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
) -> BotRouteResult:
    callback_data = get_callback_data(context)
    log_bot_event("bot_callback_click", context, callback_data=callback_data)

    if policy.can_handle_callback(callback_data):
        return policy.handle_callback(bot, context, callback_data)

    if policy.needs_policy_gate(context):
        acknowledge_callback(bot, context, "Policy required")
        return policy.start_policy_flow(bot, context, "policy.gate.callback")

    if registration.should_force_offline_message(
        context.telegram_user_id,
        callback_data=callback_data,
    ):
        acknowledge_callback(bot, context, "Offline")
        return registration.send_offline_warning(bot, context)

    if registration.can_handle_callback(callback_data):
        return registration.handle_callback(bot, context, callback_data)

    if contact_requests.can_handle_callback(callback_data):
        return contact_requests.handle_callback(bot, context, callback_data)

    if survey.can_handle_callback(callback_data):
        return survey.handle_callback(bot, context, callback_data)

    if notifications.can_handle_callback(callback_data):
        return notifications.handle_callback(bot, context, callback_data)

    acknowledge_callback(bot, context, "Unknown action")
    return send_invalid_state_message(
        bot=bot,
        context=context,
        reason=f"unknown_callback:{callback_data}",
    )
