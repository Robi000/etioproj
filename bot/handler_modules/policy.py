from django.utils import timezone

from bot.policy import (
    POLICY_BLOCK_MINUTES,
    POLICY_TEXT,
    answer_policy_question,
    get_current_question,
    get_or_create_policy_user,
    get_policy_session,
    policy_block_is_active,
    start_policy_session,
    user_has_policy_access,
)
from bot.services import TelegramBotService

from .utils import (
    BotRouteResult,
    TelegramUpdateContext,
    acknowledge_callback,
    log_bot_event,
)


def can_handle_callback(callback_data: str) -> bool:
    return callback_data.startswith("policy:")


def needs_policy_gate(context: TelegramUpdateContext) -> bool:
    if context.telegram_user_id is None:
        return True

    return not user_has_policy_access(context.telegram_user_id)


def start_policy_flow(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    route: str = "policy.start",
) -> BotRouteResult:
    telegram_user = get_or_create_policy_user(context)
    if context.chat_id is None or telegram_user is None:
        return BotRouteResult(False, "policy.no_identity", context.chat_id, context.update_id)

    if policy_block_is_active(telegram_user):
        remaining_seconds = max(
            1,
            int((telegram_user.policy_blocked_until - timezone.now()).total_seconds()),
        )
        bot.send_text(
            context.chat_id,
            (
                "Policy access is temporarily paused.\n\n"
                f"Please review the policy again and retry in about {remaining_seconds // 60 + 1} minute(s)."
            ),
            reply_markup=bot.build_policy_retry_keyboard(),
        )
        bot.send_text(context.chat_id, POLICY_TEXT)
        return BotRouteResult(False, "policy.blocked", context.chat_id, context.update_id)

    session = start_policy_session(context)
    bot.send_text(context.chat_id, POLICY_TEXT)
    send_current_question(bot, context, session)
    return BotRouteResult(True, route, context.chat_id, context.update_id)


def handle_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    callback_data: str,
) -> BotRouteResult:
    acknowledge_callback(bot, context, "Policy")
    log_bot_event("bot_callback_policy", context, callback_data=callback_data)

    if callback_data == "policy:start":
        return start_policy_flow(bot, context, "policy.restart")

    telegram_user = get_or_create_policy_user(context)
    if context.chat_id is None or context.telegram_user_id is None or telegram_user is None:
        return BotRouteResult(False, "policy.callback.no_identity", context.chat_id, context.update_id)

    if policy_block_is_active(telegram_user):
        return start_policy_flow(bot, context, "policy.blocked")

    parts = callback_data.split(":")
    if len(parts) != 4 or parts[1] != "answer":
        return start_policy_flow(bot, context, "policy.callback.invalid")

    try:
        question_index = int(parts[2])
    except ValueError:
        return start_policy_flow(bot, context, "policy.callback.bad_question")

    answer = parts[3]
    session = get_policy_session(context.telegram_user_id)
    if session is None:
        return start_policy_flow(bot, context, "policy.callback.no_session")

    correct, complete, message = answer_policy_question(
        telegram_user=telegram_user,
        session=session,
        question_index=question_index,
        answer=answer,
    )

    if not correct:
        bot.send_text(context.chat_id, POLICY_TEXT)
        bot.send_text(
            context.chat_id,
            (
                f"{message}\n\n"
                f"Access is paused for {POLICY_BLOCK_MINUTES} minutes. "
                "Please read the policy carefully before trying again."
            ),
            reply_markup=bot.build_policy_retry_keyboard(),
        )
        return BotRouteResult(False, "policy.failed", context.chat_id, context.update_id)

    if complete:
        bot.send_text(
            context.chat_id,
            "✅ Policy verification passed! 📍 Now share your location so we can find providers near you.",
        )
        bot.request_location(context.chat_id)
        return BotRouteResult(True, "policy.passed", context.chat_id, context.update_id)

    bot.send_text(context.chat_id, f"✅ {message}")
    session.refresh_from_db()
    send_current_question(bot, context, session)
    return BotRouteResult(True, "policy.answer.correct", context.chat_id, context.update_id)


def send_current_question(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    session,
) -> None:
    question_index, question = get_current_question(session)
    bot.send_text(
        context.chat_id,
        (
            f"Policy Check {question_index + 1}/3\n\n"
            f"{question.prompt}"
        ),
        reply_markup=bot.build_policy_answer_keyboard(question_index),
    )
