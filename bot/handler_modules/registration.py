from decimal import Decimal, InvalidOperation

from accounts.models import TelegramUser
from bot.location import (
    OUTSIDE_ETHIOPIA_TEXT,
    is_far_from_addis,
    store_customer_location,
    validate_ethiopia_coordinates,
)
from bot.models import BotRegistrationSession
from bot.profile_management import (
    OFFLINE_WARNING_TEXT,
    PROFILE_EDIT_PREFIX,
    PROFILE_PRICE_PREFIX,
    add_photo as add_profile_photo,
    build_delete_preview_text,
    build_profile_text,
    clear_profile_edit_state,
    delete_provider_profile,
    get_provider_service as get_managed_provider_service,
    is_edit_profile_text,
    is_go_offline_text,
    is_go_online_text,
    is_my_profile_text,
    is_profile_text_command,
    service_is_offline,
    set_profile_edit_state,
    set_visibility,
    update_age,
    update_category,
    update_description,
    update_location_from_gps,
    update_phone,
    update_price,
)
from bot.registration_state import PRICE_TYPES, RegistrationStateMachine
from bot.service_status import build_provider_service_status_text, get_provider_service
from bot.services import TelegramBotService
from services.defaults import DEFAULT_SERVICE_CATEGORY_NAMES
from services.models import ServiceCategory

from .utils import (
    BotRouteResult,
    TelegramUpdateContext,
    acknowledge_callback,
    log_bot_event,
    log_bot_warning,
)


CREATE_SERVICE_CALLBACK = "registration:create_service"
MY_SERVICE_CALLBACK = "registration:my_service"
CANCEL_CALLBACK = "registration:cancel"
CUSTOMER_BROWSE_CATEGORY_PREFIX = "customer:browse:category:"

CONTACT_COMMANDS = {"contact", "phone", "share phone", "/contact"}
LOCATION_COMMANDS = {"location", "share location", "/location"}
CANCEL_COMMANDS = {"cancel", "/cancel"}
PRICE_WAIT_PREFIX = "awaiting_price:"


def can_handle_callback(callback_data: str) -> bool:
    return callback_data.startswith(("registration:", "profile:", "customer:browse:"))


def can_handle_text(text: str) -> bool:
    normalized = text.strip().lower()
    return (
        normalized in CONTACT_COMMANDS
        or normalized in LOCATION_COMMANDS
        or normalized in CANCEL_COMMANDS
        or is_profile_text_command(text)
    )


def has_active_session(telegram_user_id: int | None) -> bool:
    if telegram_user_id is None:
        return False

    session = RegistrationStateMachine.get_session(telegram_user_id)
    if session is None:
        return False

    return session.state not in {
        BotRegistrationSession.State.COMPLETED,
        BotRegistrationSession.State.CANCELLED,
    }


def should_force_offline_message(
    telegram_user_id: int | None,
    text: str = "",
    callback_data: str = "",
) -> bool:
    if telegram_user_id is None:
        return False

    if not service_is_offline(telegram_user_id):
        return False

    if is_go_online_text(text):
        return False

    return callback_data != "profile:go_online"


def send_offline_warning(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
) -> BotRouteResult:
    if context.chat_id is not None:
        bot.send_text(
            context.chat_id,
            OFFLINE_WARNING_TEXT,
            reply_markup=bot.build_offline_menu_keyboard(),
        )

    return BotRouteResult(
        False,
        "profile.offline_locked",
        context.chat_id,
        context.update_id,
    )


def handle_text(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    text: str,
) -> BotRouteResult:
    normalized = text.strip().lower()
    log_bot_event("bot_registration_text", context, text=normalized[:80])

    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(False, "registration.text.no_identity", context.chat_id, context.update_id)

    if is_go_online_text(text):
        service = set_visibility(
            context.telegram_user_id,
            "on",
        )
        if service is None:
            bot.send_text(context.chat_id, "No provider profile was found.")
            return BotRouteResult(False, "profile.go_online.no_service", context.chat_id, context.update_id)

        bot.send_text(
            context.chat_id,
            "✅ You are online again. Customers can discover your service while it is approved and visible.",
            reply_markup=bot.build_provider_menu_keyboard(is_visible=True),
        )
        return BotRouteResult(True, "profile.go_online", context.chat_id, context.update_id)

    if is_go_offline_text(text):
        service = set_visibility(
            context.telegram_user_id,
            "off",
        )
        if service is None:
            bot.send_text(context.chat_id, "No provider profile was found.")
            return BotRouteResult(False, "profile.go_offline.no_service", context.chat_id, context.update_id)

        bot.send_text(
            context.chat_id,
            OFFLINE_WARNING_TEXT,
            reply_markup=bot.build_offline_menu_keyboard(),
        )
        return BotRouteResult(True, "profile.go_offline", context.chat_id, context.update_id)

    if is_my_profile_text(text):
        service = get_managed_provider_service(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            build_profile_text(service),
            reply_markup=bot.build_provider_menu_keyboard(
                is_visible=bool(
                    service
                    and service.visibility_status == "on"
                )
            ),
        )
        return BotRouteResult(bool(service), "profile.my_profile", context.chat_id, context.update_id)

    if is_edit_profile_text(text):
        service = get_managed_provider_service(context.telegram_user_id)
        if service is None:
            bot.send_text(context.chat_id, "No provider profile was found.")
            return BotRouteResult(False, "profile.edit.no_service", context.chat_id, context.update_id)

        bot.send_text(
            context.chat_id,
            "Choose what you want to edit.",
            reply_markup=bot.build_profile_edit_keyboard(),
        )
        return BotRouteResult(True, "profile.edit.menu", context.chat_id, context.update_id)

    if normalized in CANCEL_COMMANDS:
        RegistrationStateMachine.cancel(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            "❌ Registration cancelled. Use /start when you want to begin again.",
            reply_markup=bot.remove_reply_keyboard(),
        )
        return BotRouteResult(True, "registration.cancel.text", context.chat_id, context.update_id)

    session = RegistrationStateMachine.get_session(context.telegram_user_id)

    if session is None:
        bot.send_text(
            context.chat_id,
            "👋 No active registration is running. Press /start, then choose 🛠 Create Service.",
        )
        return BotRouteResult(False, "registration.no_active_session", context.chat_id, context.update_id)

    if normalized in CONTACT_COMMANDS:
        bot.request_contact(context.chat_id)
        return BotRouteResult(True, "registration.request_contact", context.chat_id, context.update_id)

    if normalized in LOCATION_COMMANDS:
        bot.request_location(context.chat_id)
        return BotRouteResult(True, "registration.request_location", context.chat_id, context.update_id)

    return handle_state_text(bot, context, session, text)


def handle_state_text(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    session: BotRegistrationSession,
    text: str,
) -> BotRouteResult:
    state = session.state

    if state.startswith(PROFILE_EDIT_PREFIX) or state.startswith(PROFILE_PRICE_PREFIX):
        return handle_profile_edit_text(bot, context, session, text)

    if state == BotRegistrationSession.State.SELECT_ROLE:
        bot.send_text(
            context.chat_id,
            "🎯 Please choose your role from the buttons.",
            reply_markup=bot.build_role_keyboard(),
        )
        return BotRouteResult(False, "registration.role.text_rejected", context.chat_id, context.update_id)

    if state == BotRegistrationSession.State.PROVIDER_PHONE:
        bot.request_contact(context.chat_id)
        return BotRouteResult(False, "registration.phone.text_rejected", context.chat_id, context.update_id)

    if state == BotRegistrationSession.State.SECONDARY_PHONE:
        cleaned_text = text.strip()

        if cleaned_text.lower() == "skip secondary phone":
            cleaned_text = "skip"

        success, message = RegistrationStateMachine.set_secondary_phone_number(
            session,
            cleaned_text,
        )

        if success:
            bot.send_text(
                context.chat_id,
                "⌨️ Secondary phone step closed.",
                reply_markup=bot.remove_reply_keyboard(),
            )
            bot.send_text(
                context.chat_id,
                f"{message}\n\n🏷 Step 3: Select your service category.",
                reply_markup=bot.build_category_keyboard(),
            )
        else:
            bot.send_text(
                context.chat_id,
                f"{message}\n\nYou can type another number or press Skip Secondary Phone.",
                reply_markup=bot.build_secondary_phone_keyboard(),
            )

        return BotRouteResult(
            success,
            "registration.secondary_phone.text",
            context.chat_id,
            context.update_id,
        )

    if state == BotRegistrationSession.State.CATEGORY:
        bot.send_text(
            context.chat_id,
            "🏷 Please select a category from the buttons.",
            reply_markup=bot.build_category_keyboard(),
        )
        return BotRouteResult(False, "registration.category.text_rejected", context.chat_id, context.update_id)

    if state == BotRegistrationSession.State.TITLE:
        success, message = RegistrationStateMachine.set_title(session, text)
        if success:
            bot.send_text(
                context.chat_id,
                f"{message}\n\n📝 Step 5: Write a short service description.\nExample: I provide clean home electrical repairs.",
            )
        elif session.state == BotRegistrationSession.State.CANCELLED:
            bot.send_text(
                context.chat_id,
                message,
                reply_markup=bot.remove_reply_keyboard(),
            )
        else:
            bot.send_text(
                context.chat_id,
                f"{message}\n\n🎂 Send age as digits only, for example: 28",
            )
        return BotRouteResult(success, "registration.age.text", context.chat_id, context.update_id)

    if state == BotRegistrationSession.State.DESCRIPTION:
        success, message = RegistrationStateMachine.set_description(session, text)
        if success:
            bot.send_text(
                context.chat_id,
                f"{message}\n\n📍 Step 6: Share your GPS location.",
            )
            bot.request_location(context.chat_id)
        else:
            bot.send_text(context.chat_id, f"{message}\n\nTry one clear sentence about your service.")
        return BotRouteResult(success, "registration.description.text", context.chat_id, context.update_id)

    if state == BotRegistrationSession.State.LOCATION:
        success, message = RegistrationStateMachine.set_location_from_text(session, text)
        bot.send_text(
            context.chat_id,
            f"{message}\n\n📍 Tap the GPS button below to continue.",
        )
        bot.request_location(context.chat_id)
        return BotRouteResult(success, "registration.location.manual_disabled", context.chat_id, context.update_id)

    if state.startswith(PRICE_WAIT_PREFIX):
        price_type = state.replace(PRICE_WAIT_PREFIX, "", 1)
        success, message = RegistrationStateMachine.set_price(session, price_type, text)
        session.refresh_from_db()

        if success:
            session.state = BotRegistrationSession.State.PRICES
            session.save(update_fields=["state", "updated_at"])
            bot.send_text(
                context.chat_id,
                f"{message}\n\n💵 You can add another price or finish.",
                reply_markup=bot.build_price_keyboard(session.data.get("prices", {})),
            )
        else:
            bot.send_text(
                context.chat_id,
                f"{message}\n\nSend a positive number, for example: 500",
            )
        return BotRouteResult(success, "registration.price.text", context.chat_id, context.update_id)

    if state == BotRegistrationSession.State.PRICES:
        bot.send_text(
            context.chat_id,
            "💵 Choose a price button first, then send the amount.",
            reply_markup=bot.build_price_keyboard(session.data.get("prices", {})),
        )
        return BotRouteResult(False, "registration.prices.text_rejected", context.chat_id, context.update_id)

    if state == BotRegistrationSession.State.PHOTOS:
        bot.send_text(
            context.chat_id,
            "📸 Please send a photo, or press Done With Photos after adding at least one.",
            reply_markup=bot.build_photo_keyboard(),
        )
        return BotRouteResult(False, "registration.photos.text_rejected", context.chat_id, context.update_id)

    if state == BotRegistrationSession.State.SUBMIT:
        bot.send_text(
            context.chat_id,
            "🚀 Review is ready. Press Submit Registration Draft or Cancel.",
            reply_markup=bot.build_submit_keyboard(),
        )
        return BotRouteResult(False, "registration.submit.text_rejected", context.chat_id, context.update_id)

    bot.send_text(
        context.chat_id,
        "✨ Use /start to open the menu or /cancel to stop the current registration.",
    )
    return BotRouteResult(False, f"registration.unexpected_text.{state}", context.chat_id, context.update_id)


def handle_profile_edit_text(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    session: BotRegistrationSession,
    text: str,
) -> BotRouteResult:
    state = session.state

    if context.telegram_user_id is None:
        return BotRouteResult(False, "profile.edit.no_identity", context.chat_id, context.update_id)

    if state == f"{PROFILE_EDIT_PREFIX}age":
        success, message = update_age(context.telegram_user_id, text)
        route = "profile.edit.age"
    elif state == f"{PROFILE_EDIT_PREFIX}description":
        success, message = update_description(context.telegram_user_id, text)
        route = "profile.edit.description"
    elif state == f"{PROFILE_EDIT_PREFIX}primary_phone":
        success, message = update_phone(context.telegram_user_id, text, secondary=False)
        route = "profile.edit.primary_phone"
    elif state == f"{PROFILE_EDIT_PREFIX}secondary_phone":
        success, message = update_phone(context.telegram_user_id, text, secondary=True)
        route = "profile.edit.secondary_phone"
    elif state.startswith(PROFILE_PRICE_PREFIX):
        price_type = state.replace(PROFILE_PRICE_PREFIX, "", 1)
        success, message = update_price(context.telegram_user_id, price_type, text)
        route = "profile.edit.price"
    elif state == f"{PROFILE_EDIT_PREFIX}photos":
        bot.send_text(
            context.chat_id,
            "Send a service photo, or press Done With Photos.",
            reply_markup=bot.build_profile_photo_keyboard(),
        )
        return BotRouteResult(False, "profile.edit.photos.text_rejected", context.chat_id, context.update_id)
    elif state == f"{PROFILE_EDIT_PREFIX}location":
        bot.request_location(context.chat_id)
        return BotRouteResult(False, "profile.edit.location.text_rejected", context.chat_id, context.update_id)
    else:
        clear_profile_edit_state(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            "Edit mode was reset. Choose Edit Profile again.",
            reply_markup=bot.build_provider_menu_keyboard(is_visible=True),
        )
        return BotRouteResult(False, "profile.edit.unknown_state", context.chat_id, context.update_id)

    if success:
        clear_profile_edit_state(context.telegram_user_id)
        service = get_managed_provider_service(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            f"✅ {message}\n\n{build_profile_text(service)}",
            reply_markup=bot.build_provider_menu_keyboard(
                is_visible=bool(service and service.visibility_status == "on")
            ),
        )
    else:
        bot.send_text(
            context.chat_id,
            f"⚠️ {message}\n\nTry again, or press Edit Profile to choose another field.",
            reply_markup=bot.build_profile_edit_keyboard(),
        )

    return BotRouteResult(success, route, context.chat_id, context.update_id)


def handle_reset_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
) -> BotRouteResult:
    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(
            False,
            "registration.reset.no_identity",
            context.chat_id,
            context.update_id,
        )

    RegistrationStateMachine.start_or_reset(
        telegram_user_id=context.telegram_user_id,
        chat_id=context.chat_id,
        telegram_username=context.username or "",
    )

    bot.send_text(
        context.chat_id,
        "🔄 Registration reset. Starting from the beginning.\n\nPlease select your role:",
        reply_markup=bot.build_role_keyboard(),
    )

    return BotRouteResult(
        True,
        "registration.reset",
        context.chat_id,
        context.update_id,
    )


def handle_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    callback_data: str,
) -> BotRouteResult:
    acknowledge_callback(bot, context)
    log_bot_event("bot_callback_registration", context, callback_data=callback_data)

    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(False, "registration.callback.no_identity", context.chat_id, context.update_id)

    if callback_data == "registration:reset":
        return handle_reset_callback(bot, context)

    if callback_data == CREATE_SERVICE_CALLBACK:
        telegram_user = TelegramUser.objects.filter(
            telegram_id=context.telegram_user_id,
        ).first()
        existing_service = get_managed_provider_service(context.telegram_user_id)

        if existing_service is not None:
            bot.send_text(
                context.chat_id,
                (
                    "You already have a submitted provider profile.\n\n"
                    f"{build_delete_preview_text(existing_service)}"
                ),
                reply_markup=bot.build_existing_registration_keyboard(),
            )
            return BotRouteResult(
                False,
                "registration.existing_service_blocked",
                context.chat_id,
                context.update_id,
            )

        if telegram_user is not None and (
            telegram_user.role == TelegramUser.Role.CUSTOMER
            or telegram_user.role == ""
        ):
            if not telegram_user.has_customer_location:
                bot.send_text(
                    context.chat_id,
                    "📍 To register as a provider, share your GPS location first.\n\nAfter sharing, press 🛠 Create Service again.",
                )
                bot.request_location(context.chat_id)
                return BotRouteResult(True, "customer.location_prompt", context.chat_id, context.update_id)

            # Customer with GPS → start provider registration
            session = RegistrationStateMachine.start_or_reset(
                context.telegram_user_id,
                context.chat_id,
                telegram_username=context.username,
            )
            RegistrationStateMachine.set_role(session, "provider")
            bot.send_text(
                context.chat_id,
                "👤 You're now registered as a Provider.\n\n📱 Step 1: Share your primary provider phone."
            )
            bot.request_contact(context.chat_id)
            return BotRouteResult(True, "registration.start", context.chat_id, context.update_id)

        if not context.username:
            bot.send_text(
                context.chat_id,
                "⚠️ You must set a Telegram username before registering as a provider.\n\n"
                "Open Telegram Settings → Username, set a username, then come back and press 🛠 Create Service again.",
            )
            return BotRouteResult(
                False,
                "registration.username_required",
                context.chat_id,
                context.update_id,
            )

        RegistrationStateMachine.start_or_reset(
            context.telegram_user_id,
            context.chat_id,
            telegram_username=context.username,
        )
        bot.send_text(
            context.chat_id,
            "🚀 Let's build your service registration draft.\n\n🎯 Step 1: Select your role.",
            reply_markup=bot.build_role_keyboard(),
        )
        return BotRouteResult(True, "registration.start", context.chat_id, context.update_id)

    if callback_data.startswith(CUSTOMER_BROWSE_CATEGORY_PREFIX):
        category_name = callback_data.replace(CUSTOMER_BROWSE_CATEGORY_PREFIX, "", 1)
        category = ServiceCategory.objects.filter(
            name=category_name,
            active=True,
        ).first()

        if category is None and category_name in DEFAULT_SERVICE_CATEGORY_NAMES:
            category, _ = ServiceCategory.objects.update_or_create(
                name=category_name,
                defaults={"active": True},
            )

        if category is None:
            bot.send_text(
                context.chat_id,
                "That category is not available right now. Please choose another service.",
                reply_markup=bot.build_customer_category_keyboard(),
            )
            return BotRouteResult(
                False,
                "customer.browse.category_missing",
                context.chat_id,
                context.update_id,
            )

        bot.send_text(
            context.chat_id,
            f"Open providers for {category.name}.",
            reply_markup=bot.build_mini_app_keyboard(
                "Open Providers",
                "swipe",
                query_params={"category_id": category.id},
            ),
        )
        return BotRouteResult(
            True,
            "customer.browse.open_miniapp",
            context.chat_id,
            context.update_id,
        )

    if callback_data == MY_SERVICE_CALLBACK:
        service = get_provider_service(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            build_provider_service_status_text(service),
            reply_markup=bot.build_my_service_status_keyboard(),
        )
        return BotRouteResult(True, "registration.my_service", context.chat_id, context.update_id)

    if callback_data == CANCEL_CALLBACK:
        RegistrationStateMachine.cancel(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            "❌ Registration cancelled. Use /start to reopen the menu.",
            reply_markup=bot.remove_reply_keyboard(),
        )
        return BotRouteResult(True, "registration.cancel.callback", context.chat_id, context.update_id)

    if callback_data.startswith("profile:"):
        return handle_profile_callback(bot, context, callback_data)

    session = RegistrationStateMachine.get_session(context.telegram_user_id)

    if session is None:
        bot.send_text(
            context.chat_id,
            "👋 No active registration session. Use /start and choose 🛠 Create Service.",
        )
        return BotRouteResult(False, "registration.callback.no_session", context.chat_id, context.update_id)

    if callback_data.startswith("registration:role:"):
        role = callback_data.replace("registration:role:", "", 1)
        success, message = RegistrationStateMachine.set_role(session, role)
        if success and role in {"provider", "both"}:
            TelegramUser.objects.filter(telegram_id=context.telegram_user_id).update(role=role)
            bot.send_text(context.chat_id, f"{message}\n\n📱 Step 2: Share your primary provider phone.")
            bot.request_contact(context.chat_id)
        elif success:
            RegistrationStateMachine.cancel(context.telegram_user_id)
            telegram_user = TelegramUser.objects.filter(telegram_id=context.telegram_user_id).first()
            if telegram_user and telegram_user.has_customer_location:
                bot.send_text(
                    context.chat_id,
                    "📍 Location set! Tap below to browse nearby services:",
                    reply_markup=bot.build_mini_app_keyboard(text="🛒 Open Marketplace"),
                )
            else:
                bot.send_text(
                    context.chat_id,
                    "📍 Share your GPS location to browse nearby services.\n\nAfter sharing, press /start to open the marketplace.",
                )
                bot.request_location(context.chat_id)
        else:
            bot.send_text(context.chat_id, message, reply_markup=bot.build_role_keyboard())
        return BotRouteResult(success, "registration.role.callback", context.chat_id, context.update_id)

    if callback_data.startswith("registration:category:"):
        category = callback_data.replace("registration:category:", "", 1)
        success, message = RegistrationStateMachine.set_category(session, category)

        if success:
            bot.send_text(
                context.chat_id,
                f"{message}\n\n🎂 Step 4: Send provider age as a number.\nExample: 28",
            )
        else:
            bot.send_text(
                context.chat_id,
                message,
                reply_markup=bot.build_category_keyboard(),
            )

        return BotRouteResult(
            success,
            "registration.category.callback",
            context.chat_id,
            context.update_id,
        )

    if callback_data.startswith("registration:price:"):
        price_type = callback_data.replace("registration:price:", "", 1)
        session.state = f"{PRICE_WAIT_PREFIX}{price_type}"
        session.save(update_fields=["state", "updated_at"])
        price_label = PRICE_TYPES.get(price_type, "Selected")
        bot.send_text(
            context.chat_id,
            f"💵 Send the {price_label} amount as a number.\nExample: 500",
        )
        return BotRouteResult(True, "registration.price.wait_amount", context.chat_id, context.update_id)

    if callback_data == "registration:prices_done":
        success, message = RegistrationStateMachine.finish_prices(session)
        if success:
            bot.send_text(
                context.chat_id,
                f"{message}\n\n📸 Step 8: Send 1 to 3 service photos.\nGood photos help customers trust you faster.",
                reply_markup=bot.build_photo_keyboard(),
            )
        else:
            bot.send_text(
                context.chat_id,
                message,
                reply_markup=bot.build_price_keyboard(session.data.get("prices", {})),
            )
        return BotRouteResult(success, "registration.prices_done", context.chat_id, context.update_id)

    if callback_data == "registration:photos_done":
        success, message = RegistrationStateMachine.finish_photos(session)
        session.refresh_from_db()
        if success:
            log_bot_event("bot_registration_review_requested", context)
            send_registration_review(bot, context, session)
        else:
            bot.send_text(context.chat_id, message, reply_markup=bot.build_photo_keyboard())
        return BotRouteResult(success, "registration.photos_done", context.chat_id, context.update_id)

    if callback_data == "registration:submit":
        success, message = RegistrationStateMachine.submit(session)
        service = get_managed_provider_service(context.telegram_user_id) if success else None
        bot.send_text(
            context.chat_id,
            message,
            reply_markup=(
                bot.build_provider_menu_keyboard(
                    is_visible=bool(service and service.visibility_status == "on")
                )
                if success
                else bot.remove_reply_keyboard()
            ),
        )
        if success:
            bot.send_text(
                context.chat_id,
                (
                    "⚠️ Important: Please check your Telegram privacy settings "
                    "to ensure customers can message you.\n\n"
                    'If you see the message "Profile options are limited due to '
                    'your Telegram privacy settings", go to:\n'
                    "Settings → Privacy and Security → Privacy → "
                    "Forwarded Messages → Who can add a link to my account → Everybody"
                ),
            )
            bot.send_text(
                context.chat_id,
                "📋 You can view your service in the app:",
                reply_markup=bot.build_profile_view_keyboard(),
            )
        return BotRouteResult(success, "registration.submit", context.chat_id, context.update_id)

    bot.send_text(context.chat_id, "⚠️ Unknown registration action. Use /start to reopen the menu.")
    log_bot_warning("bot_registration_unknown_callback", context, callback_data=callback_data)
    return BotRouteResult(False, "registration.unknown_callback", context.chat_id, context.update_id)


def handle_profile_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    callback_data: str,
) -> BotRouteResult:
    if context.telegram_user_id is None or context.chat_id is None:
        return BotRouteResult(False, "profile.callback.no_identity", context.chat_id, context.update_id)

    service = get_managed_provider_service(context.telegram_user_id)

    if callback_data == "profile:delete_request":
        bot.send_text(
            context.chat_id,
            build_delete_preview_text(service),
            reply_markup=bot.build_delete_profile_confirm_keyboard(),
        )
        return BotRouteResult(bool(service), "profile.delete.request", context.chat_id, context.update_id)

    if callback_data == "profile:delete_confirm":
        deleted = delete_provider_profile(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            (
                "Provider profile deleted. You can start a fresh registration from /start."
                if deleted
                else "No provider profile was found to delete."
            ),
            reply_markup=bot.remove_reply_keyboard(),
        )
        return BotRouteResult(deleted, "profile.delete.confirm", context.chat_id, context.update_id)

    if callback_data == "profile:delete_cancel":
        bot.send_text(
            context.chat_id,
            build_profile_text(service),
            reply_markup=bot.build_provider_menu_keyboard(
                is_visible=bool(service and service.visibility_status == "on")
            ),
        )
        return BotRouteResult(True, "profile.delete.cancel", context.chat_id, context.update_id)

    if callback_data == "profile:go_online":
        service = set_visibility(context.telegram_user_id, "on")
        bot.send_text(
            context.chat_id,
            "✅ You are online again. Customers can discover your service while it is approved and visible.",
            reply_markup=bot.build_provider_menu_keyboard(is_visible=True),
        )
        return BotRouteResult(bool(service), "profile.go_online.callback", context.chat_id, context.update_id)

    if callback_data == "profile:go_offline":
        service = set_visibility(context.telegram_user_id, "off")
        bot.send_text(
            context.chat_id,
            OFFLINE_WARNING_TEXT,
            reply_markup=bot.build_offline_menu_keyboard(),
        )
        return BotRouteResult(bool(service), "profile.go_offline.callback", context.chat_id, context.update_id)

    if service is None:
        bot.send_text(context.chat_id, "No provider profile was found.")
        return BotRouteResult(False, "profile.callback.no_service", context.chat_id, context.update_id)

    if callback_data == "profile:edit":
        bot.send_text(
            context.chat_id,
            "Choose what you want to edit.",
            reply_markup=bot.build_profile_edit_keyboard(),
        )
        return BotRouteResult(True, "profile.edit.menu", context.chat_id, context.update_id)

    if callback_data == "profile:edit:category":
        bot.send_text(
            context.chat_id,
            "Choose the new category.",
            reply_markup=bot.build_profile_category_keyboard(),
        )
        return BotRouteResult(True, "profile.edit.category.menu", context.chat_id, context.update_id)

    if callback_data.startswith("profile:category:"):
        category = callback_data.replace("profile:category:", "", 1)
        service = update_category(context.telegram_user_id, category)
        bot.send_text(
            context.chat_id,
            f"✅ Category updated.\n\n{build_profile_text(service)}",
            reply_markup=bot.build_provider_menu_keyboard(
                is_visible=bool(service and service.visibility_status == "on")
            ),
        )
        return BotRouteResult(True, "profile.edit.category", context.chat_id, context.update_id)

    if callback_data in {
        "profile:edit:age",
        "profile:edit:description",
        "profile:edit:primary_phone",
        "profile:edit:secondary_phone",
        "profile:edit:location",
        "profile:edit:photos",
    }:
        field = callback_data.replace("profile:edit:", "", 1)
        set_profile_edit_state(
            context.telegram_user_id,
            context.chat_id,
            f"{PROFILE_EDIT_PREFIX}{field}",
        )
        prompt_profile_edit_field(bot, context, field)
        return BotRouteResult(True, f"profile.edit.{field}.prompt", context.chat_id, context.update_id)

    if callback_data == "profile:edit:prices":
        bot.send_text(
            context.chat_id,
            "Choose which price to edit.",
            reply_markup=bot.build_profile_price_keyboard(
                {
                    price.price_type: str(price.amount)
                    for price in service.prices.all()
                }
            ),
        )
        return BotRouteResult(True, "profile.edit.prices.menu", context.chat_id, context.update_id)

    if callback_data.startswith("profile:price:"):
        price_type = callback_data.replace("profile:price:", "", 1)
        set_profile_edit_state(
            context.telegram_user_id,
            context.chat_id,
            f"{PROFILE_PRICE_PREFIX}{price_type}",
        )
        bot.send_text(
            context.chat_id,
            "Send the new price as a positive number. Example: 500",
        )
        return BotRouteResult(True, "profile.edit.price.prompt", context.chat_id, context.update_id)

    if callback_data == "profile:photos_done":
        clear_profile_edit_state(context.telegram_user_id)
        service = get_managed_provider_service(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            build_profile_text(service),
            reply_markup=bot.build_provider_menu_keyboard(
                is_visible=bool(service and service.visibility_status == "on")
            ),
        )
        return BotRouteResult(True, "profile.edit.photos.done", context.chat_id, context.update_id)

    bot.send_text(
        context.chat_id,
        "Unknown profile action. Choose Edit Profile again.",
        reply_markup=bot.build_profile_edit_keyboard(),
    )
    return BotRouteResult(False, "profile.callback.unknown", context.chat_id, context.update_id)


def prompt_profile_edit_field(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    field: str,
) -> None:
    prompts = {
        "age": "Send the new provider age. It must be 18 or older.",
        "description": "Send the new service description.",
        "primary_phone": "Send the new primary phone number.",
        "secondary_phone": "Send the secondary phone number, or send 'remove'.",
        "location": "Share the new GPS location using the button below.",
        "photos": "Send a new service photo. Maximum is 3 photos.",
    }

    if field == "location":
        bot.request_location(context.chat_id)
        return

    reply_markup = bot.build_profile_photo_keyboard() if field == "photos" else None
    bot.send_text(
        context.chat_id,
        prompts.get(field, "Send the new value."),
        reply_markup=reply_markup,
    )


def handle_contact_message(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
) -> BotRouteResult:
    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(False, "registration.contact.no_identity", context.chat_id, context.update_id)

    session = RegistrationStateMachine.get_session(context.telegram_user_id)

    if session is None:
        bot.send_text(context.chat_id, "👋 No active registration session. Use /start and choose 🛠 Create Service.")
        return BotRouteResult(False, "registration.contact.no_session", context.chat_id, context.update_id)

    if session.state != BotRegistrationSession.State.PROVIDER_PHONE:
        bot.send_text(context.chat_id, "📱 Phone sharing is only needed during the phone step.")
        return BotRouteResult(False, "registration.contact.invalid_state", context.chat_id, context.update_id)

    contact = context.message.get("contact", {}) if context.message else {}
    success, message = RegistrationStateMachine.set_phone_from_contact(session, contact)

    if success:
        bot.send_text(
            context.chat_id,
            f"{message}\n\nOptional: send a secondary phone number by text, or press Skip Secondary Phone.",
            reply_markup=bot.build_secondary_phone_keyboard(),
        )
    else:
        bot.send_text(context.chat_id, message)

    return BotRouteResult(success, "registration.contact", context.chat_id, context.update_id)


def handle_location_message(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
) -> BotRouteResult:
    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(False, "registration.location.no_identity", context.chat_id, context.update_id)

    location = context.message.get("location", {}) if context.message else {}

    if not location:
        bot.send_text(context.chat_id, "Could not read your location. Please use the GPS share button.")
        return BotRouteResult(False, "registration.location.missing_data", context.chat_id, context.update_id)

    try:
        lat = Decimal(str(location.get("latitude")))
        lon = Decimal(str(location.get("longitude")))
    except (ValueError, TypeError, InvalidOperation):
        bot.send_text(context.chat_id, "Invalid GPS coordinates received.")
        return BotRouteResult(False, "registration.location.invalid_coords", context.chat_id, context.update_id)

    user = TelegramUser.objects.filter(telegram_id=context.telegram_user_id).first()
    if user is None:
        return BotRouteResult(False, "registration.location.no_user", context.chat_id, context.update_id)

    valid, error_text = validate_ethiopia_coordinates(lat, lon)
    if not valid:
        bot.send_text(
            context.chat_id,
            error_text or OUTSIDE_ETHIOPIA_TEXT,
            reply_markup=bot.remove_reply_keyboard(),
        )
        bot.request_location(context.chat_id)
        log_bot_event("location_outside_ethiopia", context, latitude=str(lat), longitude=str(lon))
        return BotRouteResult(True, "location.outside_ethiopia", context.chat_id, context.update_id)

    if is_far_from_addis(float(lat), float(lon)):
        logger.warning(
            "event=location_far_from_addis telegram_user_id=%s lat=%s lon=%s",
            context.telegram_user_id, lat, lon,
        )

    session = RegistrationStateMachine.get_session(context.telegram_user_id)

    if session is not None and session.state == BotRegistrationSession.State.LOCATION:
        location = context.message.get("location", {}) if context.message else {}
        success, message = RegistrationStateMachine.set_location_from_gps(session, location)
        session.refresh_from_db()

        if success:
            bot.send_text(
                context.chat_id,
                "⌨️ GPS button removed.",
                reply_markup=bot.remove_reply_keyboard(),
            )
            bot.send_text(
                context.chat_id,
                f"{message}\n\n💵 Step 7: Set at least one price.",
                reply_markup=bot.build_price_keyboard(session.data.get("prices", {})),
            )
        else:
            bot.send_text(context.chat_id, message)

        return BotRouteResult(success, "registration.location", context.chat_id, context.update_id)

    if session is not None and session.state == f"{PROFILE_EDIT_PREFIX}location":
        location = context.message.get("location", {}) if context.message else {}
        success, message = update_location_from_gps(context.telegram_user_id, location)
        clear_profile_edit_state(context.telegram_user_id)
        service = get_managed_provider_service(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            f"{'✅' if success else '⚠️'} {message}",
            reply_markup=bot.remove_reply_keyboard(),
        )
        bot.send_text(
            context.chat_id,
            build_profile_text(service),
            reply_markup=bot.build_provider_menu_keyboard(
                is_visible=bool(service and service.visibility_status == "on")
            ),
        )
        return BotRouteResult(success, "profile.edit.location", context.chat_id, context.update_id)

    store_customer_location(user, lat, lon)
    log_bot_event("customer_location_stored", context, latitude=str(lat), longitude=str(lon))

    bot.send_text(
        context.chat_id,
        "✅ Location saved!",
        reply_markup=bot.remove_reply_keyboard(),
    )
    bot.send_start_menu(chat_id=context.chat_id)

    return BotRouteResult(True, "location.customer_saved", context.chat_id, context.update_id)


def handle_photo_message(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
) -> BotRouteResult:
    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(False, "registration.photo.no_identity", context.chat_id, context.update_id)

    session = RegistrationStateMachine.get_session(context.telegram_user_id)

    if session is None:
        bot.send_text(context.chat_id, "👋 No active registration session. Use /start and choose 🛠 Create Service.")
        return BotRouteResult(False, "registration.photo.no_session", context.chat_id, context.update_id)

    if session.state == f"{PROFILE_EDIT_PREFIX}photos":
        photos = context.message.get("photo", []) if context.message else []
        largest_photo = photos[-1] if photos else {}
        file_id = str(largest_photo.get("file_id", ""))
        success, message = add_profile_photo(context.telegram_user_id, file_id)
        service = get_managed_provider_service(context.telegram_user_id)
        bot.send_text(
            context.chat_id,
            f"{'✅' if success else '⚠️'} {message}",
            reply_markup=bot.build_profile_photo_keyboard(),
        )
        if success and service and not service.can_add_photo():
            clear_profile_edit_state(context.telegram_user_id)
            bot.send_text(
                context.chat_id,
                build_profile_text(service),
                reply_markup=bot.build_provider_menu_keyboard(
                    is_visible=service.visibility_status == "on"
                ),
            )
        return BotRouteResult(success, "profile.edit.photos.add", context.chat_id, context.update_id)

    if session.state != BotRegistrationSession.State.PHOTOS:
        bot.send_text(context.chat_id, "📸 Photos are accepted only during the photo step.")
        return BotRouteResult(False, "registration.photo.invalid_state", context.chat_id, context.update_id)

    photos = context.message.get("photo", []) if context.message else []
    largest_photo = photos[-1] if photos else {}
    file_id = str(largest_photo.get("file_id", ""))

    success, message = RegistrationStateMachine.add_photo(session, file_id)
    session.refresh_from_db()

    bot.send_text(
        context.chat_id,
        f"{message}\n\nPhotos saved: {len(session.data.get('photos', []))}/3",
        reply_markup=bot.build_photo_keyboard(),
    )

    return BotRouteResult(success, "registration.photo", context.chat_id, context.update_id)


def send_registration_review(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    session: BotRegistrationSession,
) -> None:
    data = session.data
    prices = data.get("prices", {})
    photos = data.get("photos", [])
    location = data.get("location", {})

    price_lines = []
    for key, label in {
        "half_day": "Half-Day",
        "full_day": "Full-Day",
        "night": "Night",
    }.items():
        if prices.get(key):
            price_lines.append(f"• {label}: {prices[key]}")

    price_text = "\n".join(price_lines) if price_lines else "No prices"

    review_text = (
        "🧾 Review your registration draft\n\n"
        f"👤 Role: {data.get('role')}\n"
        f"🔗 Telegram Username: @{data.get('telegram_username')}\n"
        f"📱 Primary Phone: {data.get('phone_number')}\n"
        f"☎️ Secondary Phone: {data.get('secondary_phone_number') or 'Not provided'}\n"
        f"🏷 Category: {data.get('category')}\n"
        f"🎂 Age: {data.get('title')}\n"
        f"📝 Description: {data.get('description')}\n"
        f"📍 Location: {location.get('latitude')}, {location.get('longitude')}\n\n"
        f"💵 Prices:\n{price_text}\n\n"
        f"📸 Photos: {len(photos)}/3\n\n"
        "Photo previews are below. The final submit button comes after the photos."
    )

    bot.send_text(
        context.chat_id,
        review_text,
    )

    for index, photo in enumerate(photos, start=1):
        bot.send_photo(
            chat_id=context.chat_id,
            photo_file_id=photo["telegram_file_id"],
            caption=f"📸 Photo {index}",
        )

    bot.send_text(
        context.chat_id,
        "🚀 Submit this registration draft?",
        reply_markup=bot.build_submit_keyboard(),
    )
