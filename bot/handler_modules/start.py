from accounts.models import TelegramUser
from bot.location import LOCATION_REQUEST_TEXT
from bot.services import TelegramBotService
from bot.profile_management import build_profile_text, get_provider_service
from bot.handler_modules.contact_requests import send_pending_alert_if_needed

from .utils import BotRouteResult, TelegramUpdateContext, log_bot_event


START_COMMANDS = {"/start", "/menu", "/help"}


def can_handle_text(text: str) -> bool:
    command = text.split(maxsplit=1)[0].lower() if text else ""
    return command in START_COMMANDS


def handle_start_command(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    text: str,
) -> BotRouteResult:
    command = text.split(maxsplit=1)[0].lower() if text else "/start"
    log_bot_event("bot_command_start", context, command=command)

    if context.chat_id is not None:
        service = get_provider_service(context.telegram_user_id)
        if service is not None:
            bot.send_text(
                context.chat_id,
                build_profile_text(service),
                reply_markup=bot.build_provider_menu_keyboard(
                    is_visible=service.visibility_status == "on"
                ),
            )
        else:
            telegram_user = TelegramUser.objects.filter(
                telegram_id=context.telegram_user_id,
            ).first()
            if telegram_user is not None and not telegram_user.has_customer_location:
                bot.send_text(
                    context.chat_id,
                    f"{LOCATION_REQUEST_TEXT}\n\nAfter sharing, the main menu will appear.",
                )
                bot.request_location(context.chat_id)
            else:
                bot.send_start_menu(chat_id=context.chat_id)

    send_pending_alert_if_needed(bot, context)

    return BotRouteResult(
        handled=True,
        route="start.command",
        chat_id=context.chat_id,
        update_id=context.update_id,
    )
