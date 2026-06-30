import logging
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections

from accounts.models import TelegramUser
from bot.service_status import (
    build_service_approval_notification_text,
    build_service_rejection_notification_text,
)
from bot.services import TelegramBotService
from services.models import PhotoChangeRequest, ServiceProfile

logger = logging.getLogger("marketplace")

_notification_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="telegram-notification",
)


def queue_service_status_notification(service_id: int, event: str) -> None:
    _notification_executor.submit(
        send_service_status_notification_safely,
        service_id,
        event,
    )
    logger.info(
        "event=service_status_notification_queued service_id=%s notification_event=%s",
        service_id,
        event,
    )


def send_service_status_notification_safely(service_id: int, event: str) -> None:
    close_old_connections()
    try:
        service = (
            ServiceProfile.objects.select_related("provider", "category")
            .filter(id=service_id)
            .first()
        )
        if service is None:
            logger.warning(
                "event=service_status_notification_missing_service service_id=%s",
                service_id,
            )
            return

        send_service_status_notification(service, event)
    except Exception as exc:
        logger.exception(
            "event=service_status_notification_failed service_id=%s notification_event=%s error=%s",
            service_id,
            event,
            exc,
        )
    finally:
        close_old_connections()


def send_service_status_notification(service: ServiceProfile, event: str) -> bool:
    bot = TelegramBotService()

    if event == ServiceProfile.ApprovalStatus.APPROVED:
        text = build_service_approval_notification_text(service)
    elif event == ServiceProfile.ApprovalStatus.REJECTED:
        text = build_service_rejection_notification_text(service)
    else:
        logger.warning(
            "event=service_status_notification_unknown_event service_id=%s notification_event=%s",
            service.id,
            event,
        )
        return False

    sent = bot.send_text(
        chat_id=service.provider.telegram_id,
        text=text,
        reply_markup=bot.build_my_service_status_keyboard(),
    )

    logger.info(
        "event=service_status_notification_sent service_id=%s provider_telegram_id=%s notification_event=%s sent=%s",
        service.id,
        service.provider.telegram_id,
        event,
        sent,
    )
    return sent


def queue_service_rejection_with_reason(provider_telegram_id: int, rejection_reason: str) -> None:
    _notification_executor.submit(
        send_service_rejection_with_reason_safely,
        provider_telegram_id,
        rejection_reason,
    )
    logger.info(
        "event=service_rejection_with_reason_queued provider_telegram_id=%s",
        provider_telegram_id,
    )


def send_service_rejection_with_reason_safely(provider_telegram_id: int, rejection_reason: str) -> None:
    close_old_connections()
    try:
        bot = TelegramBotService()
        text = (
            "❌ Your service registration was not approved.\n\n"
            f"Reason: {rejection_reason}\n\n"
            "You can start the registration process again when you are ready."
        )
        sent = bot.send_text(
            chat_id=provider_telegram_id,
            text=text,
            reply_markup=bot.build_register_again_keyboard(),
        )
        logger.info(
            "event=service_rejection_with_reason_sent provider_telegram_id=%s sent=%s",
            provider_telegram_id,
            sent,
        )
    except Exception as exc:
        logger.exception(
            "event=service_rejection_with_reason_failed provider_telegram_id=%s error=%s",
            provider_telegram_id,
            exc,
        )
    finally:
        close_old_connections()


def queue_photo_change_admin_notification(change_id: int) -> None:
    _notification_executor.submit(
        send_photo_change_admin_notification_safely,
        change_id,
    )
    logger.info(
        "event=photo_change_admin_notification_queued change_id=%s",
        change_id,
    )


def send_photo_change_admin_notification_safely(change_id: int) -> None:
    close_old_connections()
    try:
        change = (
            PhotoChangeRequest.objects.select_related(
                "service__provider", "service__category"
            )
            .filter(id=change_id)
            .first()
        )
        if change is None:
            logger.warning(
                "event=photo_change_admin_notification_missing change_id=%s",
                change_id,
            )
            return

        admins = TelegramUser.objects.filter(
            role=TelegramUser.Role.ADMIN,
        ).values_list("telegram_id", flat=True)

        bot = TelegramBotService()
        provider_name = (
            change.service.provider.telegram_username
            or change.service.provider.first_name
            or f"User {change.service.provider.telegram_id}"
        )
        text = (
            "📸 New photo change request\n\n"
            f"Provider: @{provider_name}\n"
            f"Service: {change.service.title}\n"
            f"Category: {change.service.category.name}\n"
            f"Photo #{change.order_index}\n\n"
            "Review it in the admin panel."
        )
        for admin_tg_id in admins:
            try:
                bot.send_text(chat_id=admin_tg_id, text=text)
            except Exception:
                logger.exception(
                    "event=photo_change_admin_notify_failed admin_telegram_id=%s",
                    admin_tg_id,
                )
    except Exception as exc:
        logger.exception(
            "event=photo_change_admin_notification_failed change_id=%s error=%s",
            change_id,
            exc,
        )
    finally:
        close_old_connections()
