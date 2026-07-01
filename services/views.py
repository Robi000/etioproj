import logging

from django.db import IntegrityError, transaction
from django.db.models import Avg, Q
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import TelegramUser
from accounts.views import get_telegram_user_from_auth_user
from bot.services import TelegramBotService, get_bot_api_session

from .defaults import DEFAULT_SERVICE_CATEGORY_NAMES
from .models import ServiceCategory, ServicePhoto, ServicePrice, ServiceProfile
from .serializers import (
    ServiceCategorySerializer,
    ServicePhotoCreateSerializer,
    ServicePhotoSerializer,
    ServicePriceSerializer,
    ServicePricesUpdateSerializer,
    ServiceProfileSerializer,
)

logger = logging.getLogger("marketplace")


@api_view(["GET"])
@permission_classes([AllowAny])
def services_route_check(request: Request) -> Response:
    logger.info("Services API route check requested.")
    return Response(
        {
            "success": True,
            "app": "services",
            "message": "Services API route is available.",
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_service(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    if not user_can_own_service(telegram_user):
        return Response(
            {
                "success": False,
                "error": "Only provider, both, or admin users can create a service.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if ServiceProfile.objects.filter(provider=telegram_user).exists():
        return Response(
            {
                "success": False,
                "error": "This provider already has a service profile.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ServiceProfileSerializer(
    data=request.data,
    context={"request": request},)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    try:
        with transaction.atomic():
            service = serializer.save(provider=telegram_user)
    except IntegrityError as exc:
        logger.warning(
            "Service creation failed due to integrity error for telegram_id=%s: %s",
            telegram_user.telegram_id,
            exc,
        )
        return Response(
            {
                "success": False,
                "error": "This provider already has a service profile.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "success": True,
            "service": ServiceProfileSerializer(service).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_my_service(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    service = ServiceProfile.objects.filter(provider=telegram_user).first()

    if service is None:
        return service_not_found_response()

    return Response(
        {
            "success": True,
            "service": ServiceProfileSerializer(service).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_my_service(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    service = ServiceProfile.objects.filter(provider=telegram_user).first()

    if service is None:
        return service_not_found_response()

    serializer = ServiceProfileSerializer(
    service,
    data=request.data,
    partial=True,
    context={"request": request},
)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    service = serializer.save()

    return Response(
        {
            "success": True,
            "service": ServiceProfileSerializer(service).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_my_service(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    service = ServiceProfile.objects.filter(provider=telegram_user).first()

    if service is None:
        return service_not_found_response()

    with transaction.atomic():
        if service.latitude is not None and service.longitude is not None:
            telegram_user.customer_latitude = service.latitude
            telegram_user.customer_longitude = service.longitude
        if service.city_text:
            telegram_user.city = service.city_text
        telegram_user.role = TelegramUser.Role.CUSTOMER
        telegram_user.save(update_fields=["customer_latitude", "customer_longitude", "city", "role", "updated_at"])

        from bot.models import BotRegistrationSession
        BotRegistrationSession.objects.filter(
            telegram_user_id=telegram_user.telegram_id,
        ).delete()

        service.delete()

    return Response(
        {
            "success": True,
            "deleted": True,
            "role_changed_to": "customer",
            "gps_preserved": True,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_my_service_prices(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    service = ServiceProfile.objects.filter(provider=telegram_user).first()

    if service is None:
        return service_not_found_response()

    serializer = ServicePricesUpdateSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    prices = serializer.validated_data["prices"]

    with transaction.atomic():
        service.prices.all().delete()

        created_prices = []

        for price_data in prices:
            created_prices.append(
                ServicePrice.objects.create(
                    service=service,
                    price_type=price_data["price_type"],
                    amount=price_data["amount"],
                )
            )

    return Response(
        {
            "success": True,
            "prices": ServicePriceSerializer(created_prices, many=True).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_my_service_photo(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    service = ServiceProfile.objects.filter(provider=telegram_user).first()

    if service is None:
        return service_not_found_response()

    if not service.can_add_photo():
        return Response(
            {
                "success": False,
                "error": "A service cannot have more than 3 photos.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ServicePhotoCreateSerializer(data=request.data)

    if not serializer.is_valid():
        return validation_error_response(serializer.errors)

    order_index = serializer.validated_data.get("order_index")

    if order_index is None:
        order_index = get_next_photo_order_index(service)

    if ServicePhoto.objects.filter(service=service, order_index=order_index).exists():
        return Response(
            {
                "success": False,
                "error": "This photo order_index is already used for this service.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        photo = ServicePhoto.objects.create(
            service=service,
            telegram_file_id=serializer.validated_data["telegram_file_id"],
            order_index=order_index,
        )
        from services.photo_storage import store_photo_locally
        store_photo_locally(photo)
    except Exception as exc:
        logger.warning(
            "Service photo creation failed for telegram_id=%s service_id=%s: %s",
            telegram_user.telegram_id,
            service.id,
            exc,
        )
        return Response(
            {
                "success": False,
                "error": "Service photo could not be created.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        "Service photo added for telegram_id=%s service_id=%s photo_id=%s",
        telegram_user.telegram_id,
        service.id,
        photo.id,
    )

    return Response(
        {
            "success": True,
            "photo": ServicePhotoSerializer(photo).data,
            "photo_count": service.photo_count(),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_my_service_photo(request: Request, photo_id: int) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    photo = ServicePhoto.objects.select_related("service", "service__provider").filter(
        id=photo_id
    ).first()

    if photo is None:
        return Response(
            {
                "success": False,
                "error": "Photo was not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if photo.service.provider_id != telegram_user.id:
        return Response(
            {
                "success": False,
                "error": "You cannot delete another provider's service photo.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    service = photo.service
    photo.delete()

    logger.info(
        "Service photo deleted for telegram_id=%s service_id=%s photo_id=%s",
        telegram_user.telegram_id,
        service.id,
        photo_id,
    )

    return Response(
        {
            "success": True,
            "deleted": True,
            "photo_count": service.photo_count(),
        },
        status=status.HTTP_200_OK,
    )


def get_next_photo_order_index(service: ServiceProfile) -> int:
    used_indexes = set(service.photos.values_list("order_index", flat=True))

    for index in range(1, 4):
        if index not in used_indexes:
            return index

    return 3


def linked_user_not_found_response() -> Response:
    return Response(
        {
            "success": False,
            "error": "Authenticated Django user is not linked to a Telegram marketplace user.",
        },
        status=status.HTTP_404_NOT_FOUND,
    )


def service_not_found_response() -> Response:
    return Response(
        {
            "success": False,
            "error": "No service profile exists for this user.",
        },
        status=status.HTTP_404_NOT_FOUND,
    )


def validation_error_response(errors) -> Response:
    return Response(
        {
            "success": False,
            "errors": errors,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def service_categories(request: Request) -> Response:
    categories_by_name = {
        category.name: category
        for category in ServiceCategory.objects.filter(
            active=True,
            name__in=DEFAULT_SERVICE_CATEGORY_NAMES,
        )
    }
    categories = [
        categories_by_name[category_name]
        for category_name in DEFAULT_SERVICE_CATEGORY_NAMES
        if category_name in categories_by_name
    ]
    serializer = ServiceCategorySerializer(categories, many=True)
    return Response({"success": True, "categories": serializer.data})


@api_view(["GET"])
@permission_classes([AllowAny])
def category_average_price(request: Request) -> Response:
    category_id = request.query_params.get("category_id")

    try:
        parsed_category_id = int(category_id)
    except (TypeError, ValueError):
        return Response(
            {
                "success": False,
                "error": "category_id is required and must be a positive integer.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if parsed_category_id < 1:
        return Response(
            {
                "success": False,
                "error": "category_id is required and must be a positive integer.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    rows = list(
        ServicePrice.objects.filter(
            service__category_id=parsed_category_id,
            service__category__active=True,
            service__approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        )
        .values("price_type", "service__category__name")
        .annotate(avg_amount=Avg("amount"))
    )

    averages = {
        row["price_type"]: f"{row['avg_amount']:.2f}"
        for row in rows
        if row["avg_amount"] is not None
    }
    category_name = rows[0]["service__category__name"] if rows else ""

    return Response(
        {
            "success": True,
            "category_id": parsed_category_id,
            "category_name": category_name,
            "averages": averages,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def service_photo_proxy(request: Request, photo_id: int):
    is_admin = request.user.is_authenticated and (
        request.user.is_staff or request.user.is_superuser
    )
    filters = Q(id=photo_id)
    if not is_admin:
        filters &= Q(
            service__approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            service__visibility_status=ServiceProfile.VisibilityStatus.ON,
            service__provider__is_banned=False,
            service__category__active=True,
            service__admin_forced_hidden=False,
        ) & (
            Q(service__penalty_until__isnull=True)
            | Q(service__penalty_until__lt=timezone.now())
        )
    photo = (
        ServicePhoto.objects.select_related(
            "service",
            "service__provider",
            "service__category",
        )
        .filter(filters)
        .first()
    )

    if photo is None:
        return Response(
            {
                "success": False,
                "error": "Photo was not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if photo.image:
        return redirect(photo.image.url)

    from services.photo_storage import store_photo_locally
    store_photo_locally(photo)

    if photo.image:
        return redirect(photo.image.url)

    return Response(
        {
            "success": False,
            "error": "Photo could not be loaded.",
        },
        status=status.HTTP_502_BAD_GATEWAY,
    )


def user_can_own_service(telegram_user: TelegramUser) -> bool:
    return telegram_user.role in {
        TelegramUser.Role.PROVIDER,
        TelegramUser.Role.BOTH,
        TelegramUser.Role.ADMIN,
    }
