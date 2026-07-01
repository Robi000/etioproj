import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace

from django.db import close_old_connections, transaction
from django.utils import timezone

from accounts.models import TelegramUser
from approvals.models import AdminSettings, ContactRequest
from bot.services import TelegramBotService
from services.models import ServiceProfile

logger = logging.getLogger("marketplace")

_notification_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="contact-request-notification",
)

ACTIVE_CONTACT_STATUSES = {
    ContactRequest.Status.PROVIDER_PENDING,
    ContactRequest.Status.PENDING,
    ContactRequest.Status.APPROVED,
    ContactRequest.Status.AUTO_APPROVED,
}

CONTACT_APPROVAL_VALID_HOURS = 48


@dataclass(frozen=True)
class ContactRequestWorkflowResult:
    contact_request: ContactRequest
    created: bool


def get_existing_active_contact_request(
    customer: TelegramUser,
    provider: TelegramUser,
) -> ContactRequest | None:
    cutoff = timezone.now() - timedelta(hours=CONTACT_APPROVAL_VALID_HOURS)
    return (
        ContactRequest.objects.select_related("customer", "provider", "service")
        .filter(
            customer=customer,
            provider=provider,
            status__in=ACTIVE_CONTACT_STATUSES,
        )
        .exclude(
            status__in={ContactRequest.Status.APPROVED, ContactRequest.Status.AUTO_APPROVED},
            approved_at__lt=cutoff,
        )
        .order_by("-created_at")
        .first()
    )


def create_or_reuse_provider_confirmation_request(
    customer: TelegramUser,
    service: ServiceProfile,
) -> ContactRequestWorkflowResult:
    existing_request = get_existing_active_contact_request(
        customer=customer,
        provider=service.provider,
    )

    if existing_request is not None:
        if existing_request.service_id is None:
            existing_request.service = service
            existing_request.save(update_fields=["service"])

        return ContactRequestWorkflowResult(
            contact_request=existing_request,
            created=False,
        )

    approval_cutoff = timezone.now() - timedelta(hours=CONTACT_APPROVAL_VALID_HOURS)
    recent_request = (
        ContactRequest.objects.filter(
            customer=customer,
            provider=service.provider,
            created_at__gte=approval_cutoff,
        )
        .order_by("-created_at")
        .first()
    )

    if recent_request is not None:
        return ContactRequestWorkflowResult(
            contact_request=recent_request,
            created=False,
        )

    contact_request = ContactRequest.objects.create(
        customer=customer,
        provider=service.provider,
        service=service,
        status=ContactRequest.Status.PROVIDER_PENDING,
    )

    transaction.on_commit(
        lambda: queue_provider_confirmation_message(contact_request.id)
    )

    return ContactRequestWorkflowResult(
        contact_request=contact_request,
        created=True,
    )


def queue_provider_confirmation_message(contact_request_id: int) -> None:
    _notification_executor.submit(
        send_provider_confirmation_message_safely,
        contact_request_id,
    )
    logger.info(
        "event=provider_confirmation_notification_queued contact_request_id=%s",
        contact_request_id,
    )


def queue_customer_rejection_message(contact_request_id: int) -> None:
    _notification_executor.submit(
        send_customer_rejection_message_safely,
        contact_request_id,
    )
    logger.info(
        "event=customer_provider_rejection_notification_queued contact_request_id=%s",
        contact_request_id,
    )


def maybe_auto_approve_contact_request(contact_request: ContactRequest) -> bool:
    if not AdminSettings.get_settings().auto_approve_requests:
        return False

    contact_request.status = ContactRequest.Status.AUTO_APPROVED
    contact_request.approved_at = timezone.now()
    contact_request.save(update_fields=["status", "approved_at"])
    service = contact_request.service
    if service:
        service.acceptance_count += 1
        service.save(update_fields=["acceptance_count", "updated_at"])

    transaction.on_commit(
        lambda: queue_customer_admin_decision_message(contact_request.id)
    )

    logger.info(
        "event=contact_request_auto_approved contact_request_id=%s",
        contact_request.id,
    )
    return True


def queue_customer_admin_decision_message(contact_request_id: int) -> None:
    _notification_executor.submit(
        send_customer_admin_decision_message_safely,
        contact_request_id,
    )
    logger.info(
        "event=customer_admin_decision_notification_queued contact_request_id=%s",
        contact_request_id,
    )


def send_provider_confirmation_message_safely(contact_request_id: int) -> None:
    close_old_connections()
    try:
        contact_request = get_contact_request_for_notification(contact_request_id)
        if contact_request is None:
            logger.warning(
                "event=provider_confirmation_missing_contact_request contact_request_id=%s",
                contact_request_id,
            )
            return

        bot = TelegramBotService()
        service = contact_request.service
        if service is None:
            service = SimpleNamespace(
                title="Selected service",
                category=SimpleNamespace(name="Unknown"),
                city_text="Unknown",
            )
        text = (
            "🛎 New Service Request\n\n"
            f"Customer: {contact_request.customer.get_display_name()}\n"
            f"Service: {service.title if service else 'Selected service'}\n"
            f"Category: {service.category.name if service else 'Unknown'}\n"
            f"City: {service.city_text or 'GPS location shared'}\n\n"
            "Are you available to deliver this service?"
        )
        sent = bot.send_text(
            chat_id=contact_request.provider.telegram_id,
            text=text,
            reply_markup=bot.build_contact_request_decision_keyboard(contact_request.id),
        )
        logger.info(
            "event=provider_confirmation_notification_sent contact_request_id=%s sent=%s",
            contact_request_id,
            sent,
        )
    except Exception as exc:
        logger.exception(
            "event=provider_confirmation_notification_failed contact_request_id=%s error=%s",
            contact_request_id,
            exc,
        )
    finally:
        close_old_connections()


def send_customer_rejection_message_safely(contact_request_id: int) -> None:
    close_old_connections()
    try:
        contact_request = get_contact_request_for_notification(contact_request_id)
        if contact_request is None:
            logger.warning(
                "event=customer_rejection_missing_contact_request contact_request_id=%s",
                contact_request_id,
            )
            return

        service_name = contact_request.service.title if contact_request.service else "that provider"
        bot = TelegramBotService()
        sent = bot.send_text(
            chat_id=contact_request.customer.telegram_id,
            text=(
                "Thanks for checking availability.\n\n"
                f"The provider for {service_name} is not available right now. "
                "You can choose another provider or submit a new request anytime."
            ),
        )
        logger.info(
            "event=customer_provider_rejection_notification_sent contact_request_id=%s sent=%s",
            contact_request_id,
            sent,
        )
    except Exception as exc:
        logger.exception(
            "event=customer_provider_rejection_notification_failed contact_request_id=%s error=%s",
            contact_request_id,
            exc,
        )
    finally:
        close_old_connections()


def send_customer_admin_decision_message_safely(contact_request_id: int) -> None:
    close_old_connections()
    try:
        contact_request = get_contact_request_for_notification(contact_request_id)
        if contact_request is None:
            logger.warning(
                "event=customer_admin_decision_missing_contact_request contact_request_id=%s",
                contact_request_id,
            )
            return

        bot = TelegramBotService()
        if contact_request.status in {
            ContactRequest.Status.APPROVED,
            ContactRequest.Status.AUTO_APPROVED,
        }:
            provider_contact = build_provider_contact_payload(contact_request.provider)
            lines = [f"Provider: {provider_contact['display_name']}"]
            tg = provider_contact.get('telegram_username')
            phone = provider_contact.get('secondary_phone_number')
            if phone and tg:
                lines.append(f"📞 {phone}")
                lines.append(f"💬 https://t.me/{tg.removeprefix('@')}")
            elif phone:
                lines.append(f"📞 {phone}")
            elif tg:
                lines.append(f"💬 https://t.me/{tg.removeprefix('@')}")
            text = (
                "✅ Contact request approved!\n\n"
                + "\n".join(lines) + "\n\n"
                "You can now contact the provider directly."
            )
        elif contact_request.status == ContactRequest.Status.REJECTED:
            text = (
                "Your contact request was not approved this time.\n\n"
                "You can continue exploring and choose another provider whenever you are ready."
            )
        else:
            logger.info(
                "event=customer_admin_decision_skipped contact_request_id=%s status=%s",
                contact_request_id,
                contact_request.status,
            )
            return

        sent = bot.send_text(
            chat_id=contact_request.customer.telegram_id,
            text=text,
        )
        logger.info(
            "event=customer_admin_decision_notification_sent contact_request_id=%s status=%s sent=%s",
            contact_request_id,
            contact_request.status,
            sent,
        )
    except Exception as exc:
        logger.exception(
            "event=customer_admin_decision_notification_failed contact_request_id=%s error=%s",
            contact_request_id,
            exc,
        )
    finally:
        close_old_connections()


def get_contact_request_for_notification(contact_request_id: int) -> ContactRequest | None:
    return (
        ContactRequest.objects.select_related(
            "customer",
            "provider",
            "service",
            "service__category",
        )
        .filter(id=contact_request_id)
        .first()
    )


def build_contact_request_status_payload(
    contact_request: ContactRequest,
    service: ServiceProfile | None,
) -> dict:
    contact_visible = contact_request.status in {
        ContactRequest.Status.APPROVED,
        ContactRequest.Status.AUTO_APPROVED,
    }

    payload = {
        "id": contact_request.id,
        "service_id": service.id if service is not None else contact_request.service_id,
        "provider_id": contact_request.provider_id,
        "status": contact_request.status,
        "created_at": contact_request.created_at,
        "approved_at": contact_request.approved_at,
        "contact_visible": contact_visible,
        "provider_confirmation_required": contact_request.status
        == ContactRequest.Status.PROVIDER_PENDING,
    }

    if service is not None:
        payload["service"] = {
            "id": service.id,
            "title": service.title,
            "category": service.category.name,
        }

    if contact_visible:
        payload["provider_contact"] = build_provider_contact_payload(
            contact_request.provider
        )

    return payload


def build_provider_contact_payload(provider: TelegramUser) -> dict:
    payload = {
        "display_name": provider.get_display_name(),
        "telegram_username": provider.telegram_username,
    }

    if provider.secondary_phone_number:
        payload["secondary_phone_number"] = provider.secondary_phone_number
        payload["contact_type"] = "secondary_phone_number"
        payload["contact_value"] = provider.secondary_phone_number
    else:
        payload["contact_type"] = "telegram_username"
        payload["contact_value"] = provider.telegram_username

    return payload
