import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Count
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import TelegramUser
from accounts.views import get_telegram_user_from_auth_user
from approvals.contact_workflow import queue_customer_admin_decision_message, queue_customer_rejection_message
from approvals.models import AdminSettings, ContactRequest, CustomerSurvey
from services.models import PhotoChangeRequest, ProviderDenialLog, ServiceCategory, ServicePhoto, ServiceProfile
from bot.service_notifications import queue_service_rejection_with_reason, queue_service_status_notification
from bot.models import BotRegistrationSession
from bot.services import TelegramBotService
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from .serializers import (
    AdminContactActionSerializer,
    AdminContactRequestSummarySerializer,
    AdminServiceActionSerializer,
    AdminServiceSummarySerializer,
    AdminSettingsSerializer,
    AdminSettingsUpdateSerializer,
    PhotoChangeRequestSerializer,
)

logger = logging.getLogger("marketplace")


@login_required
def admin_dashboard(request):
    if not dashboard_user_can_access(request):
        return render(
            request,
            "adminpanel/forbidden.html",
            status=403,
        )

    contact_requests = (
        ContactRequest.objects.select_related(
            "customer",
            "provider",
            "service",
            "service__category",
            "approved_by",
        )
        .order_by("-created_at")[:80]
    )
    base_services = (
        ServiceProfile.objects.select_related("provider", "category", "approved_by")
        .prefetch_related("photos", "prices")
        .order_by("-created_at")
    )
    pending_services = base_services.filter(
        approval_status=ServiceProfile.ApprovalStatus.PENDING,
    )[:80]
    approved_services_qs = base_services.filter(
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
    )
    approved_paginator = Paginator(approved_services_qs, 20)
    approved_page_num = request.GET.get("approved_page", 1)
    approved_services_page = approved_paginator.get_page(approved_page_num)
    rejected_services = base_services.filter(
        approval_status__in=[
            ServiceProfile.ApprovalStatus.REJECTED,
            ServiceProfile.ApprovalStatus.SUSPENDED,
        ],
    )[:80]
    provider_queryset = TelegramUser.objects.filter(
        role__in=[
            TelegramUser.Role.PROVIDER,
            TelegramUser.Role.BOTH,
            TelegramUser.Role.ADMIN,
        ]
    )
    customer_queryset = TelegramUser.objects.filter(
        role__in=[
            TelegramUser.Role.CUSTOMER,
            TelegramUser.Role.BOTH,
        ]
    )
    providers = provider_queryset.order_by("-created_at")[:80]
    customers = customer_queryset.order_by("-created_at")[:80]

    admin_token = None
    try:
        admin_token = Token.objects.get(user=request.user).key
    except Token.DoesNotExist:
        pass

    # Funnel analytics
    now = timezone.now()
    reminder_cutoff_start = now - timedelta(days=3)
    reminder_cutoff_end = now - timedelta(days=2)

    # Reminder users: sessions in mid-registration, updated_at between 2-3 days ago
    reminder_sessions = list(
        BotRegistrationSession.objects.filter(
            state__in=MID_REGISTRATION_STATES,
            updated_at__gte=reminder_cutoff_start,
            updated_at__lte=reminder_cutoff_end,
        )[:200]
    )
    telegram_ids = [s.telegram_user_id for s in reminder_sessions]
    telegram_users_map = {
        u.telegram_id: u
        for u in TelegramUser.objects.filter(telegram_id__in=telegram_ids)
    }
    reminder_users = []
    for session in reminder_sessions:
        user = telegram_users_map.get(session.telegram_user_id)
        if user:
            reminder_users.append({
                "id": user.id,
                "telegram_id": user.telegram_id,
                "telegram_username": user.telegram_username or "not_set",
                "first_name": user.first_name,
                "session_state": session.state,
                "session_updated_at": session.updated_at,
            })

    context = {
        "stats": {
            "pending_requests": ContactRequest.objects.filter(
                status__in=[
                    ContactRequest.Status.PROVIDER_PENDING,
                    ContactRequest.Status.PENDING,
                ]
            ).count(),
            "approved_requests": ContactRequest.objects.filter(
                status__in=[
                    ContactRequest.Status.APPROVED,
                    ContactRequest.Status.AUTO_APPROVED,
                ]
            ).count(),
            "rejected_requests": ContactRequest.objects.filter(
                status__in=[
                    ContactRequest.Status.REJECTED,
                    ContactRequest.Status.PROVIDER_REJECTED,
                ]
            ).count(),
            "service_providers": provider_queryset.count(),
            "customers": customer_queryset.count(),
            "pending_services": ServiceProfile.objects.filter(
                approval_status=ServiceProfile.ApprovalStatus.PENDING,
            ).count(),
        },
        "funnel": {
            "total_started": TelegramUser.objects.count(),
            "total_policy_passed": TelegramUser.objects.filter(
                policy_accepted_at__isnull=False
            ).count(),
            "total_mid_registration": BotRegistrationSession.objects.filter(
                state__in=MID_REGISTRATION_STATES
            ).count(),
        },
        "contact_requests": contact_requests,
        "pending_services": pending_services,
        "approved_services_page": approved_services_page,
        "rejected_services": rejected_services,
        "providers": providers,
        "customers": customers,
        "settings": AdminSettings.get_settings(),
        "reminder_users": reminder_users,
        "photo_changes": PhotoChangeRequest.objects.filter(
            status=PhotoChangeRequest.Status.PENDING,
        ).select_related(
            "service__provider", "service__category"
        ).order_by("-created_at")[:50],
        "contact_status": ContactRequest.Status,
        "service_status": ServiceProfile.ApprovalStatus,
        "session_state": BotRegistrationSession.State,
        "admin_tg_user": get_dashboard_admin_telegram_user(request),
        "admin_token": admin_token,
    }

    return render(request, "adminpanel/dashboard.html", context)


@login_required
@require_POST
def dashboard_contact_action(request, contact_request_id: int, action: str):
    if not dashboard_user_can_access(request):
        return redirect("adminpanel-dashboard")

    contact_request = get_object_or_404(ContactRequest, id=contact_request_id)
    admin_user = get_dashboard_admin_telegram_user(request)
    if admin_user is None:
        logger.warning("event=admin_action_no_telegram_user user=%s action=%s", request.user.username, action)

    if action == "approve":
        if contact_request.status != ContactRequest.Status.PENDING:
            messages.error(
                request,
                "Provider must accept this request before admin approval.",
            )
        else:
            contact_request.status = ContactRequest.Status.APPROVED
            contact_request.approved_by = admin_user
            contact_request.approved_at = timezone.now()
            contact_request.save()
            transaction.on_commit(
                lambda: queue_customer_admin_decision_message(contact_request.id)
            )
            messages.success(request, "Contact request approved and customer notified.")
    elif action == "reject":
        contact_request.status = ContactRequest.Status.REJECTED
        contact_request.approved_by = admin_user
        contact_request.approved_at = None
        contact_request.save()
        transaction.on_commit(
            lambda: queue_customer_admin_decision_message(contact_request.id)
        )
        messages.success(request, "Contact request rejected and customer notified.")
    else:
        messages.error(request, "Unknown contact action.")

    return redirect("adminpanel-dashboard")


@login_required
@require_POST
def dashboard_service_action(request, service_id: int, action: str):
    if not dashboard_user_can_access(request):
        return redirect("adminpanel-dashboard")

    service = get_object_or_404(ServiceProfile, id=service_id)
    admin_user = get_dashboard_admin_telegram_user(request)
    if admin_user is None:
        logger.warning("event=admin_action_no_telegram_user user=%s action=%s", request.user.username, action)

    if action == "approve":
        service.approval_status = ServiceProfile.ApprovalStatus.APPROVED
        service.approved_by = admin_user
        service.approved_at = timezone.now()
        service.save()
        transaction.on_commit(
            lambda: queue_service_status_notification(
                service.id,
                ServiceProfile.ApprovalStatus.APPROVED,
            )
        )
        messages.success(request, "Service approved and provider notified.")
    elif action == "reject":
        service.approval_status = ServiceProfile.ApprovalStatus.REJECTED
        service.approved_by = admin_user
        service.approved_at = None
        service.save()
        transaction.on_commit(
            lambda: queue_service_status_notification(
                service.id,
                ServiceProfile.ApprovalStatus.REJECTED,
            )
        )
        messages.success(request, "Service rejected and provider notified.")
    else:
        messages.error(request, "Unknown service action.")

    return redirect("adminpanel-dashboard")


@api_view(["GET"])
@permission_classes([AllowAny])
def adminpanel_route_check(request: Request) -> Response:
    logger.info("Adminpanel API route check requested.")
    return Response(
        {
            "success": True,
            "app": "adminpanel",
            "message": "Admin Panel API route is available.",
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_services(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)

    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    services = (
        ServiceProfile.objects.select_related(
            "provider",
            "category",
            "approved_by",
        )
        .filter(
            approval_status=ServiceProfile.ApprovalStatus.PENDING,
        )
        .order_by("created_at")
    )

    return Response(
        {
            "success": True,
            "services": AdminServiceSummarySerializer(services, many=True).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_service(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)

    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    serializer = AdminServiceActionSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    service = ServiceProfile.objects.filter(
        id=serializer.validated_data["service_id"]
    ).first()

    if service is None:
        return Response(
            {
                "success": False,
                "error": "Service was not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    service.approval_status = ServiceProfile.ApprovalStatus.APPROVED
    service.approved_by = admin_user
    service.approved_at = timezone.now()
    service.save()
    transaction.on_commit(
        lambda: queue_service_status_notification(
            service.id,
            ServiceProfile.ApprovalStatus.APPROVED,
        )
    )

    logger.info(
        "Service approved admin_telegram_id=%s service_id=%s",
        admin_user.telegram_id if admin_user else "staff",
        service.id,
    )

    return Response(
        {
            "success": True,
            "service": AdminServiceSummarySerializer(service).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_service(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    serializer = AdminServiceActionSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    rejection_reason = serializer.validated_data.get("rejection_reason")
    if not rejection_reason or not rejection_reason.strip():
        return Response(
            {
                "success": False,
                "error": "Rejection reason is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    rejection_reason = rejection_reason.strip()
    if len(rejection_reason) < 10:
        return Response(
            {
                "success": False,
                "error": "Rejection reason must be at least 10 characters.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    service = ServiceProfile.objects.select_related("provider").filter(
        id=serializer.validated_data["service_id"]
    ).first()

    if service is None:
        return Response(
            {
                "success": False,
                "error": "Service was not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    provider = service.provider
    provider_telegram_id = provider.telegram_id

    with transaction.atomic():
        service.rejection_reason = rejection_reason
        service.approval_status = ServiceProfile.ApprovalStatus.REJECTED
        service.approved_by = admin_user
        service.approved_at = None
        service.save()

        service.photos.all().delete()
        service.prices.all().delete()
        service.delete()

        provider.role = TelegramUser.Role.CUSTOMER
        provider.save(update_fields=["role", "updated_at"])

        BotRegistrationSession.objects.filter(
            telegram_user_id=provider_telegram_id
        ).delete()

    transaction.on_commit(
        lambda: queue_service_rejection_with_reason(
            provider_telegram_id,
            rejection_reason,
        )
    )

    logger.info(
        "Service rejected and provider reset admin_telegram_id=%s provider_telegram_id=%s service_id=%s",
        admin_user.telegram_id if admin_user else "staff",
        provider_telegram_id,
        service.id,
    )

    return Response(
        {
            "success": True,
            "message": "Service rejected and provider notified.",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_contacts(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)

    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    contact_requests = (
        ContactRequest.objects.select_related(
            "customer",
            "provider",
            "service",
            "service__category",
            "approved_by",
        )
        .filter(
            status=ContactRequest.Status.PENDING,
        )
        .order_by("created_at")
    )

    return Response(
        {
            "success": True,
            "contact_requests": AdminContactRequestSummarySerializer(
                contact_requests,
                many=True,
            ).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_contact(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)

    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    serializer = AdminContactActionSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    contact_request = ContactRequest.objects.filter(
        id=serializer.validated_data["contact_request_id"]
    ).first()

    if contact_request is None:
        return Response(
            {
                "success": False,
                "error": "Contact request was not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if contact_request.status != ContactRequest.Status.PENDING:
        return Response(
            {
                "success": False,
                "error": "Provider must accept the request before admin approval.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    contact_request.status = ContactRequest.Status.APPROVED
    contact_request.approved_by = admin_user
    contact_request.approved_at = timezone.now()
    contact_request.save()
    transaction.on_commit(
        lambda: queue_customer_admin_decision_message(contact_request.id)
    )

    logger.info(
        "Contact request approved admin_telegram_id=%s contact_request_id=%s",
        admin_user.telegram_id if admin_user else "staff",
        contact_request.id,
    )

    return Response(
        {
            "success": True,
            "contact_request": AdminContactRequestSummarySerializer(contact_request).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_contact(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)

    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    serializer = AdminContactActionSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    contact_request = ContactRequest.objects.filter(
        id=serializer.validated_data["contact_request_id"]
    ).first()

    if contact_request is None:
        return Response(
            {
                "success": False,
                "error": "Contact request was not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    contact_request.status = ContactRequest.Status.REJECTED
    contact_request.approved_by = admin_user
    contact_request.approved_at = None
    contact_request.save()
    transaction.on_commit(
        lambda: queue_customer_admin_decision_message(contact_request.id)
    )

    logger.info(
        "Contact request rejected admin_telegram_id=%s contact_request_id=%s",
        admin_user.telegram_id if admin_user else "staff",
        contact_request.id,
    )

    return Response(
        {
            "success": True,
            "contact_request": AdminContactRequestSummarySerializer(contact_request).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_admin_settings(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)

    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    serializer = AdminSettingsUpdateSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    settings_object = AdminSettings.get_settings()

    for field, value in serializer.validated_data.items():
        setattr(settings_object, field, value)

    settings_object.save()

    logger.info(
        "Admin settings updated admin_telegram_id=%s fields=%s",
        admin_user.telegram_id if admin_user else "staff",
        list(serializer.validated_data.keys()),
    )

    return Response(
        {
            "success": True,
            "settings": AdminSettingsSerializer(settings_object).data,
        },
        status=status.HTTP_200_OK,
    )


def get_admin_telegram_user(request: Request) -> TelegramUser | None:
    if request.user.is_staff or request.user.is_superuser:
        return get_telegram_user_from_auth_user(request.user)

    telegram_user = get_telegram_user_from_auth_user(request.user)
    if telegram_user is None:
        return None

    if telegram_user.is_banned:
        return None

    if telegram_user.role != TelegramUser.Role.ADMIN:
        return None

    return telegram_user


def dashboard_user_can_access(request) -> bool:
    if request.user.is_staff or request.user.is_superuser:
        return True

    telegram_user = get_dashboard_admin_telegram_user(request)
    return bool(telegram_user)


def get_dashboard_admin_telegram_user(request) -> TelegramUser | None:
    telegram_user = get_telegram_user_from_auth_user(request.user)
    if telegram_user is None:
        return None

    if telegram_user.is_banned:
        return None

    if telegram_user.role == TelegramUser.Role.ADMIN:
        return telegram_user

    if request.user.is_staff or request.user.is_superuser:
        return telegram_user

    return None


def admin_forbidden_response() -> Response:
    return Response(
        {
            "success": False,
            "error": "Admin permission is required.",
        },
        status=status.HTTP_403_FORBIDDEN,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_provider_verified(request: Request, provider_id: int) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    provider = TelegramUser.objects.filter(id=provider_id).first()
    if provider is None:
        return Response(
            {"success": False, "error": "Provider not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    provider.is_verified = not provider.is_verified
    provider.save(update_fields=["is_verified", "updated_at"])

    logger.info(
        "event=admin_toggle field=is_verified provider_id=%s new_value=%s",
        provider_id,
        provider.is_verified,
    )

    return Response(
        {"success": True, "is_verified": provider.is_verified},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_provider_tested(request: Request, provider_id: int) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    provider = TelegramUser.objects.filter(id=provider_id).first()
    if provider is None:
        return Response(
            {"success": False, "error": "Provider not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    provider.admin_tested_badge = not provider.admin_tested_badge
    provider.save(update_fields=["admin_tested_badge", "updated_at"])

    logger.info(
        "event=admin_toggle field=admin_tested_badge provider_id=%s new_value=%s",
        provider_id,
        provider.admin_tested_badge,
    )

    return Response(
        {"success": True, "admin_tested_badge": provider.admin_tested_badge},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_service_admin_visibility(request: Request, service_id: int) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    service = ServiceProfile.objects.filter(id=service_id).first()
    if service is None:
        return Response(
            {"success": False, "error": "Service was not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    service.admin_forced_hidden = not service.admin_forced_hidden
    service.save(update_fields=["admin_forced_hidden", "updated_at"])

    logger.info(
        "event=admin_toggle field=admin_forced_hidden service_id=%s new_value=%s",
        service_id,
        service.admin_forced_hidden,
    )

    return Response(
        {"success": True, "admin_forced_hidden": service.admin_forced_hidden},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def process_timeouts(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    cutoff = timezone.now() - timedelta(hours=24)
    expired_requests = ContactRequest.objects.select_related(
        "provider", "service"
    ).filter(
        status=ContactRequest.Status.PROVIDER_PENDING,
        created_at__lt=cutoff,
    )

    processed_count = 0
    for contact_request in expired_requests:
        with transaction.atomic():
            contact_request.status = ContactRequest.Status.PROVIDER_REJECTED
            contact_request.approved_by = None
            contact_request.approved_at = None
            contact_request.save(update_fields=["status", "approved_by", "approved_at"])
            transaction.on_commit(
                lambda cid=contact_request.id: queue_customer_rejection_message(cid)
            )

            service = contact_request.service
            if service:
                service.denial_count += 1
                service.save(update_fields=["denial_count", "updated_at"])
                ProviderDenialLog.objects.create(
                    service=service,
                    reason=ProviderDenialLog.DenialReason.TIMEOUT,
                    contact_request=contact_request,
                )
                _apply_timeout_penalty_if_needed(service)

        logger.info(
            "event=timeout_denial_applied contact_request_id=%s provider_id=%s",
            contact_request.id,
            contact_request.provider_id,
        )
        processed_count += 1

    return Response(
        {"success": True, "processed_count": processed_count},
        status=status.HTTP_200_OK,
    )


def _apply_timeout_penalty_if_needed(service) -> None:
    from datetime import timedelta
    from django.utils import timezone

    total_requests = ContactRequest.objects.filter(provider=service.provider).count()
    if total_requests < 10:
        return

    denial_ratio = service.denial_count / total_requests
    if denial_ratio <= 0.75:
        return

    is_first_penalty = service.penalty_count == 0
    duration = timedelta(days=7) if is_first_penalty else timedelta(days=15)
    service.penalty_until = timezone.now() + duration
    service.visibility_status = ServiceProfile.VisibilityStatus.OFF
    service.penalty_count += 1
    service.save(update_fields=["penalty_until", "visibility_status", "penalty_count", "updated_at"])

    logger.info(
        "event=provider_penalty_applied service_id=%s provider_id=%s penalty_count=%s duration_days=%s source=timeout",
        service.id,
        service.provider_id,
        service.penalty_count,
        7 if is_first_penalty else 15,
    )


MID_REGISTRATION_STATES = [
    BotRegistrationSession.State.SELECT_ROLE,
    BotRegistrationSession.State.PROVIDER_PHONE,
    BotRegistrationSession.State.SECONDARY_PHONE,
    BotRegistrationSession.State.CATEGORY,
    BotRegistrationSession.State.TITLE,
    BotRegistrationSession.State.DESCRIPTION,
    BotRegistrationSession.State.LOCATION,
    BotRegistrationSession.State.PRICES,
    BotRegistrationSession.State.PHOTOS,
    BotRegistrationSession.State.SUBMIT,
]


def _build_continue_registration_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Continue Registration", callback_data="registration:create_service")]
    ])


def _send_registration_reminder(telegram_user_id: int) -> bool:
    bot = TelegramBotService()
    text = (
        "👋 You started registering your service profile but haven't finished yet.\n\n"
        "Tap below to continue where you left off:"
    )
    return bot.send_text(
        chat_id=telegram_user_id,
        text=text,
        reply_markup=_build_continue_registration_keyboard(),
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_registration_reminder(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    user_id = request.data.get("telegram_user_id")
    if not user_id:
        return Response(
            {"success": False, "error": "telegram_user_id is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = TelegramUser.objects.get(id=user_id)
    except TelegramUser.DoesNotExist:
        return Response(
            {"success": False, "error": "User not found or no active session."},
            status=status.HTTP_404_NOT_FOUND,
        )

    session = BotRegistrationSession.objects.filter(
        telegram_user_id=user.telegram_id,
        state__in=MID_REGISTRATION_STATES,
    ).first()
    if session is None:
        return Response(
            {"success": False, "error": "User not found or no active session."},
            status=status.HTTP_404_NOT_FOUND,
        )

    sent = _send_registration_reminder(user.telegram_id)
    if not sent:
        logger.warning(
            "event=registration_reminder_failed admin_telegram_id=%s target_id=%s reason=send_failed",
            admin_user.telegram_id if admin_user else "staff",
            user_id,
        )
        return Response(
            {"success": False, "error": "Failed to send Telegram message."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    logger.info(
        "event=registration_reminder_sent admin_telegram_id=%s target_id=%s",
        admin_user.telegram_id if admin_user else "staff",
        user_id,
    )

    return Response({"success": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_mass_reminders(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    now = timezone.now()
    reminder_cutoff_start = now - timedelta(days=3)
    reminder_cutoff_end = now - timedelta(days=2)

    reminder_sessions = BotRegistrationSession.objects.filter(
        state__in=MID_REGISTRATION_STATES,
        updated_at__gte=reminder_cutoff_start,
        updated_at__lte=reminder_cutoff_end,
    )[:200]

    sent_count = 0
    failed_count = 0

    for session in reminder_sessions:
        try:
            sent = _send_registration_reminder(session.telegram_user_id)
            if sent:
                sent_count += 1
                logger.info(
                    "event=registration_reminder_sent admin_telegram_id=%s target_telegram_id=%s",
                    admin_user.telegram_id if admin_user else "staff",
                    session.telegram_user_id,
                )
            else:
                failed_count += 1
                logger.warning(
                    "event=registration_reminder_failed admin_telegram_id=%s target_telegram_id=%s reason=send_failed",
                    admin_user.telegram_id if admin_user else "staff",
                    session.telegram_user_id,
                )
        except Exception:
            failed_count += 1
            logger.warning(
                "event=registration_reminder_failed admin_telegram_id=%s target_telegram_id=%s reason=exception",
                admin_user.telegram_id if admin_user else "staff",
                session.telegram_user_id,
            )

    logger.info(
        "event=mass_reminders_sent admin_telegram_id=%s sent=%s failed=%s",
        admin_user.telegram_id if admin_user else "staff",
        sent_count,
        failed_count,
    )

    return Response(
        {
            "success": True,
            "sent_count": sent_count,
            "failed_count": failed_count,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def request_location_updates(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    cutoff = timezone.now() - timedelta(days=30)
    bot = TelegramBotService()
    sent_count = 0

    providers = (
        ServiceProfile.objects.filter(
            approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        )
        .filter(
            models.Q(location_update_requested_at__isnull=True)
            | models.Q(location_update_requested_at__lt=cutoff)
        )
        .select_related("provider")
    )

    location_keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "Share GPS Location",
                    request_location=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    for service in providers:
        try:
            ok = bot.send_text(
                chat_id=service.provider.telegram_id,
                text="Please confirm or update your service location. Tap below to share your current GPS location.",
                reply_markup=location_keyboard,
            )
            if ok:
                service.location_update_requested_at = timezone.now()
                ServiceProfile.objects.filter(pk=service.pk).update(
                    location_update_requested_at=service.location_update_requested_at,
                )
                sent_count += 1
                logger.info(
                    "event=location_update_requested provider_id=%s service_id=%s",
                    service.provider_id, service.id,
                )
        except Exception:
            logger.warning(
                "event=location_update_request_failed provider_id=%s service_id=%s",
                service.provider_id, service.id,
            )

    logger.info(
        "event=location_updates_batch_sent admin_telegram_id=%s sent_count=%s",
        admin_user.telegram_id if admin_user else "staff",
        sent_count,
    )

    return Response(
        {"success": True, "sent_count": sent_count},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_photo_changes(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    requests_qs = PhotoChangeRequest.objects.filter(
        status=PhotoChangeRequest.Status.PENDING,
    ).select_related(
        "service__provider", "service__category"
    ).order_by("-created_at")

    return Response(
        {
            "success": True,
            "photo_changes": PhotoChangeRequestSerializer(requests_qs, many=True).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_photo_change(request: Request, request_id: int) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    change = get_object_or_404(
        PhotoChangeRequest.objects.select_related("service"),
        id=request_id,
        status=PhotoChangeRequest.Status.PENDING,
    )

    ServicePhoto.objects.update_or_create(
        service=change.service,
        order_index=change.order_index,
        defaults={"telegram_file_id": change.new_file_id},
    )

    change.status = PhotoChangeRequest.Status.APPROVED
    change.approved_at = timezone.now()
    change.save(update_fields=["status", "approved_at"])

    provider = change.service.provider
    bot = TelegramBotService()
    try:
        bot.send_text(
            chat_id=provider.telegram_id,
            text="✅ Your photo change request has been approved.",
        )
    except Exception:
        logger.exception("event=photo_change_approve_notify_failed provider_id=%s", provider.id)

    logger.info(
        "event=photo_change_approved request_id=%s service_id=%s admin_telegram_id=%s",
        change.id, change.service_id, admin_user.telegram_id if admin_user else "staff",
    )

    return Response(
        {"success": True, "photo_change": PhotoChangeRequestSerializer(change).data},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_photo_change(request: Request, request_id: int) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    change = get_object_or_404(
        PhotoChangeRequest.objects.select_related("service__provider"),
        id=request_id,
        status=PhotoChangeRequest.Status.PENDING,
    )

    change.status = PhotoChangeRequest.Status.REJECTED
    change.save(update_fields=["status"])

    provider = change.service.provider
    bot = TelegramBotService()
    try:
        bot.send_text(
            chat_id=provider.telegram_id,
            text="❌ Your photo change request was not approved by the admin.",
        )
    except Exception:
        logger.exception("event=photo_change_reject_notify_failed provider_id=%s", provider.id)

    logger.info(
        "event=photo_change_rejected request_id=%s service_id=%s admin_telegram_id=%s",
        change.id, change.service_id, admin_user.telegram_id if admin_user else "staff",
    )

    return Response(
        {"success": True, "photo_change": PhotoChangeRequestSerializer(change).data},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_surveys(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    cutoff = timezone.now() - timedelta(days=2)
    bot = TelegramBotService()
    sent_count = 0

    eligible_requests = ContactRequest.objects.filter(
        status__in=[
            ContactRequest.Status.APPROVED,
            ContactRequest.Status.AUTO_APPROVED,
        ],
        approved_at__lt=cutoff,
        survey__isnull=True,
    ).select_related("customer", "provider", "service")

    for cr in eligible_requests:
        CustomerSurvey.objects.create(
            contact_request=cr,
            sent_at=timezone.now(),
        )

        provider_username = cr.provider.telegram_username or cr.provider.first_name or "the provider"
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Yes",
                        callback_data=f"survey:yes:{cr.id}",
                    ),
                    InlineKeyboardButton(
                        "❌ No",
                        callback_data=f"survey:no:{cr.id}",
                    ),
                ]
            ]
        )
        try:
            ok = bot.send_text(
                chat_id=cr.customer.telegram_id,
                text=(
                    f"👋 Hi! Did you receive the service from @{provider_username}?"
                ),
                reply_markup=reply_markup,
            )
            if ok:
                sent_count += 1
                logger.info(
                    "event=survey_sent contact_request_id=%s customer_id=%s",
                    cr.id, cr.customer_id,
                )
        except Exception:
            logger.warning(
                "event=survey_send_failed contact_request_id=%s customer_id=%s",
                cr.id, cr.customer_id,
            )

    logger.info(
        "event=surveys_batch_sent admin_telegram_id=%s sent_count=%s",
        admin_user.telegram_id if admin_user else "staff",
        sent_count,
    )

    return Response(
        {"success": True, "sent_count": sent_count},
        status=status.HTTP_200_OK,
    )


_advertisement_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="advertisement",
)

MAX_CUSTOMERS_PER_BATCH = 500


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_advertisement(request: Request) -> Response:
    admin_user = get_admin_telegram_user(request)
    if admin_user is None and not (request.user.is_staff or request.user.is_superuser):
        return admin_forbidden_response()

    top_services = list(
        ServiceProfile.objects.filter(
            approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
            admin_forced_hidden=False,
        )
        .order_by("-likes_count")[:3]
        .only("id", "title", "category", "city_text")
    )

    photo_service_map: dict[int, ServiceProfile] = {}
    for service in top_services:
        first_photo = ServicePhoto.objects.filter(
            service=service, order_index=1
        ).first()
        if first_photo:
            photo_service_map[service.id] = service

    popular_categories = (
        ServiceCategory.objects.filter(
            service_profiles__approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            service_profiles__visibility_status=ServiceProfile.VisibilityStatus.ON,
            service_profiles__admin_forced_hidden=False,
        )
        .annotate(approved_count=Count("service_profiles"))
        .filter(approved_count__gt=0)
        .order_by("-approved_count")[:3]
    )

    for category in popular_categories:
        if len(photo_service_map) >= 3:
            break
        featured = (
            ServiceProfile.objects.filter(
                category=category,
                approval_status=ServiceProfile.ApprovalStatus.APPROVED,
                visibility_status=ServiceProfile.VisibilityStatus.ON,
                admin_forced_hidden=False,
            )
            .exclude(id__in=photo_service_map.keys())
            .select_related("category")
            .first()
        )
        if featured:
            first_photo = ServicePhoto.objects.filter(
                service=featured, order_index=1
            ).first()
            if first_photo:
                photo_service_map[featured.id] = featured

    photos_to_send = []
    for sid in list(photo_service_map.keys())[:3]:
        service = photo_service_map[sid]
        photo = ServicePhoto.objects.filter(service=service, order_index=1).first()
        if photo:
            category_name = service.category.name if hasattr(service, "category") and service.category else ""
            photos_to_send.append(
                {
                    "photo_file_id": photo.telegram_file_id,
                    "caption": f"{service.title} - {category_name} 📍 {service.city_text}",
                }
            )

    customers = TelegramUser.objects.filter(
        role__in=[TelegramUser.Role.CUSTOMER, TelegramUser.Role.BOTH],
        policy_accepted_at__isnull=False,
    )[:MAX_CUSTOMERS_PER_BATCH]

    customer_ids = list(customers.values_list("id", flat=True))
    bot = TelegramBotService()
    photo_send_count = 0
    failure_count = 0

    def send_photos_to_customer(customer_id: int) -> int:
        from django.db import close_old_connections

        try:
            chat = TelegramUser.objects.filter(id=customer_id).only("telegram_id").first()
            if chat is None:
                return 0
            sent = 0
            for photo in photos_to_send:
                try:
                    ok = bot.send_photo(
                        chat_id=chat.telegram_id,
                        photo_file_id=photo["photo_file_id"],
                        caption=photo["caption"],
                    )
                    if ok:
                        sent += 1
                        logger.info(
                            "event=advertisement_photo_sent customer_id=%s telegram_id=%s",
                            customer_id, chat.telegram_id,
                        )
                    else:
                        logger.warning(
                            "event=advertisement_photo_failed customer_id=%s telegram_id=%s",
                            customer_id, chat.telegram_id,
                        )
                except Exception:
                    logger.warning(
                        "event=advertisement_photo_error customer_id=%s telegram_id=%s",
                        customer_id, chat.telegram_id,
                    )
            return sent
        finally:
            close_old_connections()

    futures = []
    for cid in customer_ids:
        futures.append(
            _advertisement_executor.submit(send_photos_to_customer, cid)
        )

    for f in futures:
        try:
            photo_send_count += f.result(timeout=30)
        except Exception:
            failure_count += 1

    logger.info(
        "event=advertisement_batch_sent admin_telegram_id=%s customers_targeted=%s photos_sent=%s failures=%s",
        admin_user.telegram_id if admin_user else "staff",
        len(customer_ids),
        photo_send_count,
        failure_count,
    )

    return Response(
        {
            "success": True,
            "customers_targeted": len(customer_ids),
            "photos_sent": photo_send_count,
        },
        status=status.HTTP_200_OK,
    )


def validation_error_response(errors) -> Response:
    return Response(
        {
            "success": False,
            "errors": errors,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )
