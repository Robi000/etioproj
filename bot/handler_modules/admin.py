from bot.services import TelegramBotService

from .utils import BotRouteResult, TelegramUpdateContext, log_bot_event


ADMIN_COMMANDS = {"/admin"}


def can_handle_text(text: str) -> bool:
    command = text.split(maxsplit=1)[0].lower() if text else ""
    return command in ADMIN_COMMANDS


def handle_admin_command(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    text: str,
) -> BotRouteResult:
    command = text.split(maxsplit=1)[0].lower() if text else "/admin"
    log_bot_event("bot_command_admin", context, command=command)

    if context.chat_id is not None:
        bot.send_text(
            chat_id=context.chat_id,
            text=(
                "Admin tools are protected. Open the marketplace app or Django admin "
                "with an authorized admin account to review services and contacts."
            ),
            reply_markup=bot.build_mini_app_keyboard("Open Marketplace"),
        )

    return BotRouteResult(
        handled=True,
        route="admin.command",
        chat_id=context.chat_id,
        update_id=context.update_id,
    )
