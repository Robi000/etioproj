import logging

from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from approvals.contact_workflow import maybe_auto_approve_contact_request, queue_customer_rejection_message
from approvals.models import ContactRequest
from bot.services import TelegramBotService
from services.models import ProviderDenialLog, ServiceProfile

from swipes.models import SavedServiceRequest

from .utils import (
    BotRouteResult,
    TelegramUpdateContext,
    acknowledge_callback,
    log_bot_event,
)

logger = logging.getLogger("marketplace")

CONTACT_CALLBACK_PREFIX = "contact:"
SAVE_CALLBACK_PREFIX = "service:save:"
PROFILE_MANAGEMENT_CALLBACK_PREFIXES = (
    "profile:",
    "registration:my_service",
)
PROFILE_MANAGEMENT_TEXTS = {
    "my profile",
    "profile",
    "/profile",
    "edit profile",
    "edit",
    "/edit",
    "go offline",
    "offline",
    "/offline",
    "go online",
    "online",
    "/online",
}
PENALTY_WARNING_TEXT = (
    "⚠️ Warning: You have denied {denial_count} contact requests. "
    "If your denial rate exceeds 85% after 20 requests, you will be temporarily suspended. "
    "To avoid this, toggle your visibility Off when you are unavailable."
)


def can_handle_callback(callback_data: str) -> bool:
    return callback_data.startswith(CONTACT_CALLBACK_PREFIX) or callback_data.startswith(SAVE_CALLBACK_PREFIX)


def handle_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    callback_data: str,
) -> BotRouteResult:
    acknowledge_callback(bot, context, "Received")
    log_bot_event("bot_callback_contact_request", context, callback_data=callback_data)

    if callback_data.startswith(SAVE_CALLBACK_PREFIX):
        return handle_save_callback(bot, context, callback_data)

    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(False, "contact.callback.no_identity", context.chat_id, context.update_id)

    parts = callback_data.split(":")
    if len(parts) != 3 or parts[1] not in {"accept", "reject"}:
        bot.send_text(context.chat_id, "This service request action is not valid anymore.")
        return BotRouteResult(False, "contact.callback.invalid", context.chat_id, context.update_id)

    action = parts[1]
    try:
        contact_request_id = int(parts[2])
    except ValueError:
        bot.send_text(context.chat_id, "This service request action is not valid anymore.")
        return BotRouteResult(False, "contact.callback.bad_id", context.chat_id, context.update_id)

    contact_request = (
        ContactRequest.objects.select_related("provider", "customer", "service", "service__category")
        .filter(id=contact_request_id)
        .first()
    )

    if contact_request is None:
        bot.send_text(context.chat_id, "This service request was not found.")
        return BotRouteResult(False, "contact.callback.not_found", context.chat_id, context.update_id)

    if contact_request.provider.telegram_id != context.telegram_user_id:
        bot.send_text(context.chat_id, "Only the selected provider can answer this request.")
        return BotRouteResult(False, "contact.callback.wrong_provider", context.chat_id, context.update_id)

    if contact_request.status != ContactRequest.Status.PROVIDER_PENDING:
        bot.send_text(
            context.chat_id,
            f"This request is already {contact_request.get_status_display().lower()}.",
        )
        return BotRouteResult(False, "contact.callback.already_answered", context.chat_id, context.update_id)

    if action == "accept":
        return accept_contact_request(bot, context, contact_request)

    return reject_contact_request(bot, context, contact_request)


def accept_contact_request(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    contact_request: ContactRequest,
) -> BotRouteResult:
    with transaction.atomic():
        contact_request.status = ContactRequest.Status.PENDING
        contact_request.save(update_fields=["status"])
        auto_approved = maybe_auto_approve_contact_request(contact_request)

    service = contact_request.service
    if auto_approved:
        bot.send_text(
            context.chat_id,
            (
                "✅ Availability confirmed.\n\n"
                "Your contact has been automatically shared with the customer. "
                "They will receive your contact details shortly."
            ),
        )
    else:
        bot.send_text(
            context.chat_id,
            (
                "✅ Availability confirmed.\n\n"
                "This request has been forwarded to admin for final approval. "
                "Your contact will be shared only after admin approval."
            ),
        )

    return BotRouteResult(
        True,
        "contact.accepted",
        context.chat_id,
        context.update_id,
    )


def reject_contact_request(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    contact_request: ContactRequest,
) -> BotRouteResult:
    with transaction.atomic():
        contact_request.status = ContactRequest.Status.PROVIDER_REJECTED
        contact_request.approved_by = None
        contact_request.approved_at = None
        contact_request.save(update_fields=["status", "approved_by", "approved_at"])
        transaction.on_commit(
            lambda: queue_customer_rejection_message(contact_request.id)
        )

        service = contact_request.service
        if service:
            service.denial_count += 1
            service.save(update_fields=["denial_count", "updated_at"])
            ProviderDenialLog.objects.create(
                service=service,
                reason=ProviderDenialLog.DenialReason.MANUAL_REJECT,
                contact_request=contact_request,
            )
            _evaluate_and_apply_penalty(service)

    service_title = service.title if service else "this service"
    bot.send_text(
        context.chat_id,
        (
            "❌ Request rejected.\n\n"
            f"The customer will be told that you are not available for {service_title} right now."
        ),
    )

    _send_denial_warning_if_needed(bot, context, service)

    return BotRouteResult(
        True,
        "contact.rejected",
        context.chat_id,
        context.update_id,
    )


def _evaluate_and_apply_penalty(service: ServiceProfile) -> None:
    total_requests = ContactRequest.objects.filter(provider=service.provider).count()
    if total_requests < 20:
        return

    denial_ratio = service.denial_count / total_requests
    if denial_ratio <= 0.85:
        return

    is_first_penalty = service.penalty_count == 0
    duration = timedelta(days=7) if is_first_penalty else timedelta(days=15)
    service.penalty_until = timezone.now() + duration
    service.visibility_status = ServiceProfile.VisibilityStatus.OFF
    service.penalty_count += 1

    service.save(update_fields=["denial_count", "penalty_until", "visibility_status", "penalty_count", "updated_at"])

    logger.info(
        "event=provider_penalty_applied service_id=%s provider_id=%s penalty_count=%s duration_days=%s",
        service.id,
        service.provider_id,
        service.penalty_count,
        7 if is_first_penalty else 15,
    )


def _send_denial_warning_if_needed(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    service: ServiceProfile | None,
) -> None:
    if service is None:
        return
    if service.denial_count >= 5 and context.chat_id is not None:
        bot.send_text(
            context.chat_id,
            PENALTY_WARNING_TEXT.format(denial_count=service.denial_count),
            reply_markup=bot.build_offline_menu_keyboard(),
        )
        log_bot_event(
            "provider_denial_warning_sent",
            context,
            denial_count=service.denial_count,
        )


def handle_save_callback(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    callback_data: str,
) -> BotRouteResult:
    from accounts.models import TelegramUser

    if context.chat_id is None or context.telegram_user_id is None:
        return BotRouteResult(False, "save.callback.no_identity", context.chat_id, context.update_id)

    parts = callback_data.split(":")
    if len(parts) != 3:
        bot.send_text(context.chat_id, "This action is not valid anymore.")
        return BotRouteResult(False, "save.callback.invalid", context.chat_id, context.update_id)

    try:
        service_id = int(parts[2])
    except ValueError:
        bot.send_text(context.chat_id, "This action is not valid anymore.")
        return BotRouteResult(False, "save.callback.bad_id", context.chat_id, context.update_id)

    customer = TelegramUser.objects.filter(
        telegram_id=context.telegram_user_id
    ).first()

    if customer is None or not customer.is_customer:
        bot.send_text(context.chat_id, "Only customers can save services.")
        return BotRouteResult(False, "save.callback.not_customer", context.chat_id, context.update_id)

    service = ServiceProfile.objects.filter(id=service_id).first()
    if service is None:
        bot.send_text(context.chat_id, "Service not found.")
        return BotRouteResult(False, "save.callback.not_found", context.chat_id, context.update_id)

    existing = SavedServiceRequest.objects.filter(
        customer=customer, service_id=service_id
    ).first()

    if existing:
        existing.delete()
        bot.send_text(
            context.chat_id,
            f"✅ Removed \"{service.title}\" from your saved services.",
        )
        log_bot_event("bot_service_unsaved", context, service_id=service_id)
        return BotRouteResult(True, "save.unsaved", context.chat_id, context.update_id)

    saved_count = SavedServiceRequest.objects.filter(customer=customer).count()
    if saved_count >= 3:
        bot.send_text(
            context.chat_id,
            "You can save up to 3 services. Please remove a saved service first.",
        )
        return BotRouteResult(False, "save.max_reached", context.chat_id, context.update_id)

    SavedServiceRequest.objects.create(customer=customer, service_id=service_id)
    bot.send_text(
        context.chat_id,
        f"💾 \"{service.title}\" has been saved! You can view your saved services anytime.",
    )
    log_bot_event("bot_service_saved", context, service_id=service_id)
    return BotRouteResult(True, "save.saved", context.chat_id, context.update_id)


def send_pending_alert_if_needed(
    bot: TelegramBotService,
    context: TelegramUpdateContext,
    callback_data: str = "",
) -> None:
    if context.telegram_user_id is None or context.chat_id is None:
        return

    if callback_data.startswith(CONTACT_CALLBACK_PREFIX):
        return

    if is_profile_management_interaction(context, callback_data):
        return

    cutoff = timezone.now() - timedelta(hours=1)
    pending_request = ContactRequest.objects.filter(
        provider__telegram_id=context.telegram_user_id,
        status=ContactRequest.Status.PROVIDER_PENDING,
        created_at__lt=cutoff,
    ).select_related("service", "customer").first()
    if pending_request is None:
        return

    customer = pending_request.customer
    service = pending_request.service
    service_title = service.title if service else "this service"

    bot.send_text(
        context.chat_id,
        (
            f"🔔 You have a pending service request from {customer.get_display_name()}!\n\n"
            f"Service: {service_title}\n\n"
            "Please respond:"
        ),
        reply_markup=bot.build_contact_request_decision_keyboard(pending_request.id),
    )
    log_bot_event(
        "provider_pending_request_alert_sent",
        context,
        contact_request_id=pending_request.id,
    )


def is_profile_management_interaction(
    context: TelegramUpdateContext,
    callback_data: str = "",
) -> bool:
    if callback_data.startswith(PROFILE_MANAGEMENT_CALLBACK_PREFIXES):
        return True

    text = ""
    if context.message:
        text = str(context.message.get("text", ""))

    normalized_text = " ".join(text.strip().lower().split())
    return normalized_text in PROFILE_MANAGEMENT_TEXTS
