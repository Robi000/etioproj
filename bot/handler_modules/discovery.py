from accounts.models import TelegramUser
from bot.location import LOCATION_REQUEST_TEXT
from bot.services import TelegramBotService

from .utils import BotRouteResult, TelegramUpdateContext, log_bot_event


DISCOVERY_COMMANDS = {"/discover", "/search", "/find"}


def can_handle_text(text: str) -> bool:
    command = text.split(maxsplit=1)[0].lower() if text else ""
    return command in DISCOVERY_COMMANDS


def _customer_needs_location(telegram_user_id: int) -> bool:
    user = TelegramUser.objects.filter(telegram_id=telegram_user_id).first()
    if user is None:
        return False
    return not user.has_customer_location


def handle_discovery_command(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    text: str,
) -> BotRouteResult:
    command = text.split(maxsplit=1)[0].lower() if text else "/discover"
    log_bot_event("bot_command_discovery", context, command=command)

    if context.chat_id is not None:
        if context.telegram_user_id is not None and _customer_needs_location(context.telegram_user_id):
            bot.send_text(
                chat_id=context.chat_id,
                text=LOCATION_REQUEST_TEXT,
            )
            bot.request_location(context.chat_id)
            return BotRouteResult(
                handled=True,
                route="discovery.location_required",
                chat_id=context.chat_id,
                update_id=context.update_id,
            )
        bot.send_text(
            chat_id=context.chat_id,
            text=(
                "Discovery is available in the marketplace app. "
                "Open it to choose service type, location, swipe view, or grid view."
            ),
            reply_markup=bot.build_mini_app_keyboard("Open Discovery", "swipe"),
        )

    return BotRouteResult(
        handled=True,
        route="discovery.command",
        chat_id=context.chat_id,
        update_id=context.update_id,
    )


def handle_fallback_text(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    text: str,
) -> BotRouteResult:
    log_bot_event("bot_text_fallback", context, text=text[:80])

    if context.chat_id is not None:
        bot.send_text(
            chat_id=context.chat_id,
            text=(
                "I can help you open the marketplace, manage your service, "
                "or check notifications. Use /start to choose an option."
            ),
        )

    return BotRouteResult(
        handled=True,
        route="discovery.text_fallback",
        chat_id=context.chat_id,
        update_id=context.update_id,
    )
