import logging

from django.db import transaction
from django.db.models import F
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import TelegramUser
from accounts.views import get_telegram_user_from_auth_user
from approvals.contact_workflow import (
    build_contact_request_status_payload,
    create_or_reuse_provider_confirmation_request,
    get_existing_active_contact_request,
)
from approvals.models import ContactRequest
from approvals.usage_limits import (
    build_contact_usage_payload,
    evaluate_contact_request_creation,
)
from services.models import ServiceProfile
from swipes.models import SwipeHistory

from matching.serializers import build_discovery_card
from swipes.models import SavedServiceRequest

from .serializers import SaveServiceSerializer, SwipeActionSerializer

logger = logging.getLogger("marketplace")


@api_view(["GET"])
@permission_classes([AllowAny])
def swipes_route_check(request: Request) -> Response:
    logger.info("Swipes API route check requested.")
    return Response(
        {
            "success": True,
            "app": "swipes",
            "message": "Swipes API route is available.",
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def swipe_like(request: Request) -> Response:
    customer = get_telegram_user_from_auth_user(request.user)

    if customer is None:
        return linked_user_not_found_response()

    if customer.is_banned:
        return banned_user_response()

    if customer.role == TelegramUser.Role.PROVIDER:
        return Response(
            {"success": False, "error": "Providers cannot send contact requests."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = SwipeActionSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    service = get_discoverable_service(serializer.validated_data["service_id"])

    if service is None:
        return Response(
            {
                "success": False,
                "error": "Service is not available for swipe actions.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if service.provider_id == customer.id:
        return Response(
            {
                "success": False,
                "error": "You cannot like your own service.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing_contact_request = get_existing_active_contact_request(
        customer=customer,
        provider=service.provider,
    )

    if existing_contact_request is None:
        usage_decision = evaluate_contact_request_creation(customer)

        if not usage_decision.allowed:
            return contact_request_usage_limited_response(usage_decision)

    with transaction.atomic():
        swipe = SwipeHistory.objects.create(
            customer=customer,
            service=service,
            swipe_status=SwipeHistory.SwipeStatus.LIKED,
        )
        ServiceProfile.objects.filter(id=service.id).update(
            likes_count=F("likes_count") + 1,
        )

        workflow_result = create_or_reuse_provider_confirmation_request(
            customer=customer,
            service=service,
        )
        contact_request = workflow_result.contact_request

    logger.info(
        "Swipe like recorded customer_id=%s service_id=%s contact_request_id=%s",
        customer.id,
        service.id,
        contact_request.id,
    )

    return Response(
        {
            "success": True,
            "swipe": {
                "id": swipe.id,
                "service_id": service.id,
                "swipe_status": swipe.swipe_status,
                "reset_at": swipe.reset_at,
            },
            "contact_request": build_contact_request_status_payload(contact_request, service),
            "provider_protection": build_contact_usage_payload(
                evaluate_contact_request_creation(customer)
            ),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def swipe_dislike(request: Request) -> Response:
    customer = get_telegram_user_from_auth_user(request.user)

    if customer is None:
        return linked_user_not_found_response()

    if customer.is_banned:
        return banned_user_response()

    serializer = SwipeActionSerializer(data=request.data)

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

    swipe = SwipeHistory.objects.create(
        customer=customer,
        service=service,
        swipe_status=SwipeHistory.SwipeStatus.DISLIKED,
    )

    logger.info(
        "Swipe dislike recorded customer_id=%s service_id=%s",
        customer.id,
        service.id,
    )

    return Response(
        {
            "success": True,
            "swipe": {
                "id": swipe.id,
                "service_id": service.id,
                "swipe_status": swipe.swipe_status,
                "reset_at": swipe.reset_at,
            },
        },
        status=status.HTTP_201_CREATED,
    )


def get_discoverable_service(service_id: int) -> ServiceProfile | None:
    return (
        ServiceProfile.objects.select_related("provider", "category")
        .filter(
            id=service_id,
            approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
            provider__is_banned=False,
            category__active=True,
            admin_forced_hidden=False,
        )
        .filter(
            Q(penalty_until__isnull=True) | Q(penalty_until__lt=timezone.now())
        )
        .first()
    )


def contact_request_usage_limited_response(usage_decision) -> Response:
    response = Response(
        {
            "success": False,
            "error": usage_decision.message,
            "provider_protection": build_contact_usage_payload(usage_decision),
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )

    if usage_decision.retry_after_seconds:
        response["Retry-After"] = str(usage_decision.retry_after_seconds)

    return response


def linked_user_not_found_response() -> Response:
    return Response(
        {
            "success": False,
            "error": "Authenticated Django user is not linked to a Telegram marketplace user.",
        },
        status=status.HTTP_404_NOT_FOUND,
    )


def banned_user_response() -> Response:
    return Response(
        {
            "success": False,
            "error": "Banned users cannot perform this action.",
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def validation_error_response(errors) -> Response:
    return Response(
        {
            "success": False,
            "errors": errors,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_service(request: Request) -> Response:
    customer = get_telegram_user_from_auth_user(request.user)

    if customer is None:
        return linked_user_not_found_response()

    if customer.is_banned:
        return banned_user_response()

    serializer = SaveServiceSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    service_id = serializer.validated_data["service_id"]

    existing = SavedServiceRequest.objects.filter(
        customer=customer, service_id=service_id
    ).first()

    if existing:
        return Response(
            {"success": True, "saved": True, "created_at": existing.created_at},
            status=status.HTTP_200_OK,
        )

    if SavedServiceRequest.objects.filter(customer=customer).count() >= 3:
        return Response(
            {
                "success": False,
                "error": "You can save up to 3 services. Please remove a saved service before saving a new one.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    saved = SavedServiceRequest.objects.create(
        customer=customer, service_id=service_id
    )

    return Response(
        {"success": True, "saved": True, "created_at": saved.created_at},
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def unsave_service(request: Request, service_id: int) -> Response:
    customer = get_telegram_user_from_auth_user(request.user)

    if customer is None:
        return linked_user_not_found_response()

    if customer.is_banned:
        return banned_user_response()

    deleted_count, _ = SavedServiceRequest.objects.filter(
        customer=customer, service_id=service_id
    ).delete()

    return Response(
        {"success": True, "deleted": deleted_count > 0},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def saved_services(request: Request) -> Response:
    customer = get_telegram_user_from_auth_user(request.user)

    if customer is None:
        return linked_user_not_found_response()

    if customer.is_banned:
        return banned_user_response()

    saved_entries = (
        SavedServiceRequest.objects.filter(customer=customer)
        .select_related(
            "service__provider",
            "service__category",
        )
        .prefetch_related(
            "service__prices",
            "service__photos",
        )
    )

    services = []
    for entry in saved_entries:
        card = build_discovery_card(entry.service, distance_km=None)
        card["saved_at"] = entry.created_at
        services.append(card)

    return Response(
        {"success": True, "services": services},
        status=status.HTTP_200_OK,
    )

