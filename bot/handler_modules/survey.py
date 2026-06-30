import logging

from django.utils import timezone

from approvals.models import CustomerSurvey
from bot.services import TelegramBotService
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .utils import (
    BotRouteResult,
    TelegramUpdateContext,
    acknowledge_callback,
    log_bot_event,
)

logger = logging.getLogger("marketplace")

SURVEY_CALLBACK_PREFIX = "survey:"


def can_handle_callback(callback_data: str) -> bool:
    return callback_data.startswith(SURVEY_CALLBACK_PREFIX)


def handle_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    callback_data: str,
) -> BotRouteResult:
    acknowledge_callback(bot, context, "Received")
    log_bot_event("bot_callback_survey", context, callback_data=callback_data)

    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(False, "survey.callback.no_identity", context.chat_id, context.update_id)

    parts = callback_data.split(":")

    if len(parts) == 4 and parts[1] == "reason":
        return handle_reason_callback(bot, context, parts[2], parts[3])

    if len(parts) != 3 or parts[1] not in {"yes", "no"}:
        bot.send_text(context.chat_id, "This survey action is not valid anymore.")
        return BotRouteResult(False, "survey.callback.invalid", context.chat_id, context.update_id)

    action = parts[1]
    try:
        contact_request_id = int(parts[2])
    except ValueError:
        bot.send_text(context.chat_id, "This survey action is not valid anymore.")
        return BotRouteResult(False, "survey.callback.bad_id", context.chat_id, context.update_id)

    try:
        survey = CustomerSurvey.objects.get(contact_request_id=contact_request_id)
    except CustomerSurvey.DoesNotExist:
        bot.send_text(context.chat_id, "Survey not found.")
        return BotRouteResult(False, "survey.callback.not_found", context.chat_id, context.update_id)

    if action == "yes":
        return handle_yes_response(bot, context, survey)
    return handle_no_response(bot, context, survey)


def handle_yes_response(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    survey: CustomerSurvey,
) -> BotRouteResult:
    survey.response = "yes"
    survey.responded_at = timezone.now()
    survey.save(update_fields=["response", "responded_at"])

    bot.send_text(
        context.chat_id,
        "Thank you for your feedback! 😊",
    )
    log_bot_event("survey_responded_yes", context, contact_request_id=survey.contact_request_id)
    return BotRouteResult(True, "survey.yes", context.chat_id, context.update_id)


def handle_no_response(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    survey: CustomerSurvey,
) -> BotRouteResult:
    survey.response = "no"
    survey.responded_at = timezone.now()
    survey.save(update_fields=["response", "responded_at"])

    reason_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💰 Price changed",
                    callback_data=f"survey:reason:price_change:{survey.contact_request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🚗 Transport cost > 1000 ETB",
                    callback_data=f"survey:reason:transport_cost:{survey.contact_request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "💵 Advance > 30%",
                    callback_data=f"survey:reason:advance_too_high:{survey.contact_request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "📵 Provider not responding",
                    callback_data=f"survey:reason:provider_not_responding:{survey.contact_request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🚫 Didn't come after advance",
                    callback_data=f"survey:reason:provider_no_show:{survey.contact_request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "❤️ Personal preference",
                    callback_data=f"survey:reason:personal:{survey.contact_request_id}",
                )
            ],
        ]
    )

    bot.send_text(
        context.chat_id,
        "Sorry to hear that. What was the issue?",
        reply_markup=reason_markup,
    )
    log_bot_event("survey_responded_no", context, contact_request_id=survey.contact_request_id)
    return BotRouteResult(True, "survey.no", context.chat_id, context.update_id)


def handle_reason_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    reason: str,
    contact_request_id: str,
) -> BotRouteResult:
    try:
        int_id = int(contact_request_id)
    except ValueError:
        bot.send_text(context.chat_id, "This survey action is not valid anymore.")
        return BotRouteResult(False, "survey.reason.bad_id", context.chat_id, context.update_id)

    valid_reasons = {choice[0] for choice in CustomerSurvey._meta.get_field("no_reason").choices if choice[0]}
    if reason not in valid_reasons:
        bot.send_text(context.chat_id, "This survey action is not valid anymore.")
        return BotRouteResult(False, "survey.reason.invalid", context.chat_id, context.update_id)

    try:
        survey = CustomerSurvey.objects.get(contact_request_id=int_id)
    except CustomerSurvey.DoesNotExist:
        bot.send_text(context.chat_id, "Survey not found.")
        return BotRouteResult(False, "survey.reason.not_found", context.chat_id, context.update_id)

    survey.no_reason = reason
    survey.save(update_fields=["no_reason"])

    bot.send_text(
        context.chat_id,
        "Thank you for letting us know. We'll use this to improve the service.",
    )
    log_bot_event("survey_reason_provided", context, reason=reason, contact_request_id=int_id)
    return BotRouteResult(True, "survey.reason", context.chat_id, context.update_id)
