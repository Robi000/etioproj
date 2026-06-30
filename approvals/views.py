import logging

from django.db import transaction
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
from bot.location import LOCATION_REQUEST_TEXT
from services.models import ServiceProfile

from .serializers import (
    ContactRequestCreateSerializer,
    ContactRequestStatusSerializer,
)

logger = logging.getLogger("marketplace")


@api_view(["GET"])
@permission_classes([AllowAny])
def approvals_route_check(request: Request) -> Response:
    logger.info("Approvals API route check requested.")
    return Response(
        {
            "success": True,
            "app": "approvals",
            "message": "Approvals API route is available.",
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_contact_request(request: Request) -> Response:
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

    if not customer.has_customer_location:
        return Response(
            {
                "success": False,
                "error": "LOCATION_REQUIRED",
                "message": LOCATION_REQUEST_TEXT,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ContactRequestCreateSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    service = get_discoverable_service(serializer.validated_data["service_id"])

    if service is None:
        return Response(
            {
                "success": False,
                "error": "Service is not available for contact requests.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if service.provider_id == customer.id:
        return Response(
            {
                "success": False,
                "error": "You cannot request contact for your own service.",
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
        workflow_result = create_or_reuse_provider_confirmation_request(
            customer=customer,
            service=service,
        )
        contact_request = workflow_result.contact_request

    logger.info(
        "Contact request created/reused customer_id=%s service_id=%s contact_request_id=%s",
        customer.id,
        service.id,
        contact_request.id,
    )

    return Response(
        {
            "success": True,
            "contact_request": build_contact_request_status_payload(contact_request, service),
            "provider_protection": build_contact_usage_payload(
                evaluate_contact_request_creation(customer)
            ),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def contact_request_status(request: Request) -> Response:
    customer = get_telegram_user_from_auth_user(request.user)

    if customer is None:
        return linked_user_not_found_response()

    serializer = ContactRequestStatusSerializer(data=request.query_params)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

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

    contact_request = ContactRequest.objects.select_related("service").filter(
        customer=customer,
        provider=service.provider,
    ).order_by("-created_at").first()

    if contact_request is None:
        return Response(
            {
                "success": True,
                "contact_request": None,
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {
            "success": True,
            "contact_request": build_contact_request_status_payload(contact_request, service),
        },
        status=status.HTTP_200_OK,
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

