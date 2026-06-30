import logging

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from miniapp.auth import (
    TelegramInitDataValidationError,
    TelegramMiniAppAuthService,
)
from services.models import ServiceProfile

from .models import TelegramUser
from .serializers import (
    CustomerLocationSerializer,
    ProfileLocationUpdateSerializer,
    ProfileUpdateSerializer,
    ProfileVisibilityUpdateSerializer,
    TelegramAuthRequestSerializer,
    TelegramUserSerializer,
)

logger = logging.getLogger("marketplace")


@api_view(["GET"])
@permission_classes([AllowAny])
def accounts_route_check(request: Request) -> Response:
    logger.info("Accounts API route check requested.")
    return Response(
        {
            "success": True,
            "app": "accounts",
            "message": "Accounts API route is available.",
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def telegram_auth(request: Request) -> Response:
    request_serializer = TelegramAuthRequestSerializer(data=request.data)

    if not request_serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": request_serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    init_data = request_serializer.validated_data["init_data"]

    try:
        validated_data = TelegramMiniAppAuthService.validate_init_data(init_data)
    except TelegramInitDataValidationError as exc:
        logger.warning("Telegram Mini App authentication failed: %s", exc)
        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    with transaction.atomic():
        telegram_user = sync_telegram_user(validated_data.user)
        django_user = sync_django_auth_user(telegram_user)
        token, _ = Token.objects.get_or_create(user=django_user)

    logger.info(
        "Telegram Mini App authentication succeeded for telegram_id=%s",
        telegram_user.telegram_id,
    )

    return Response(
        {
            "success": True,
            "token": token.key,
            "user": TelegramUserSerializer(telegram_user).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return Response(
            {
                "success": False,
                "error": "Authenticated Django user is not linked to a Telegram marketplace user.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "success": True,
            "user": TelegramUserSerializer(telegram_user).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_profile(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return Response(
            {
                "success": False,
                "error": "Authenticated Django user is not linked to a Telegram marketplace user.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = ProfileUpdateSerializer(data=request.data, partial=True)

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    for field, value in serializer.validated_data.items():
        setattr(telegram_user, field, value)

    telegram_user.save()

    logger.info("Profile updated for telegram_id=%s", telegram_user.telegram_id)

    return Response(
        {
            "success": True,
            "user": TelegramUserSerializer(telegram_user).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_profile_location(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return Response(
            {
                "success": False,
                "error": "Authenticated Django user is not linked to a Telegram marketplace user.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    service_profile = get_service_profile_for_user(telegram_user)

    if service_profile is None:
        return Response(
            {
                "success": False,
                "error": "No service profile exists for this user. Location is stored on provider service profiles.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = ProfileLocationUpdateSerializer(data=request.data, partial=True)

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    latitude = serializer.validated_data.get("latitude")
    longitude = serializer.validated_data.get("longitude")
    city_text = serializer.validated_data.get("city_text")

    if latitude is not None and longitude is not None:
        service_profile.latitude = latitude
        service_profile.longitude = longitude

        from services.models import CityLocation
        city_name = CityLocation.get_city_for_coordinates(longitude, latitude)
        if city_name:
            service_profile.city_text = city_name
            telegram_user.city = city_name
            telegram_user.save(update_fields=["city", "updated_at"])

    if city_text is not None:
        service_profile.city_text = city_text
        telegram_user.city = city_text
        telegram_user.save(update_fields=["city", "updated_at"])

    has_gps = service_profile.latitude is not None and service_profile.longitude is not None
    has_city = bool(service_profile.city_text)

    if has_gps and has_city:
        service_profile.location_source = ServiceProfile.LocationSource.BOTH
    elif has_gps:
        service_profile.location_source = ServiceProfile.LocationSource.GPS
    else:
        service_profile.location_source = ServiceProfile.LocationSource.CITY_TEXT

    service_profile.save()

    logger.info("Profile location updated for telegram_id=%s", telegram_user.telegram_id)

    return Response(
        {
            "success": True,
            "location": {
                "latitude": str(service_profile.latitude) if service_profile.latitude is not None else None,
                "longitude": str(service_profile.longitude) if service_profile.longitude is not None else None,
                "city_text": service_profile.city_text,
                "location_source": service_profile.location_source,
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH", "POST"])
@permission_classes([IsAuthenticated])
def update_profile_visibility(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return Response(
            {
                "success": False,
                "error": "Authenticated Django user is not linked to a Telegram marketplace user.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    service_profile = get_service_profile_for_user(telegram_user)

    if service_profile is None:
        return Response(
            {
                "success": False,
                "error": "No service profile exists for this user. Visibility is available only for provider service profiles.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = ProfileVisibilityUpdateSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    service_profile.visibility_status = serializer.validated_data["visibility_status"]
    service_profile.save()

    logger.info(
        "Profile visibility updated for telegram_id=%s visibility=%s",
        telegram_user.telegram_id,
        service_profile.visibility_status,
    )

    return Response(
        {
            "success": True,
            "visibility_status": service_profile.visibility_status,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH", "POST"])
@permission_classes([IsAuthenticated])
def update_customer_location(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return Response(
            {
                "success": False,
                "error": "Authenticated Django user is not linked to a Telegram marketplace user.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = CustomerLocationSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    telegram_user.customer_latitude = serializer.validated_data["latitude"]
    telegram_user.customer_longitude = serializer.validated_data["longitude"]
    telegram_user.customer_location_updated_at = timezone.now()

    from services.models import CityLocation
    city_name = CityLocation.get_city_for_coordinates(
        serializer.validated_data["longitude"],
        serializer.validated_data["latitude"],
    )
    if city_name:
        telegram_user.city = city_name

    telegram_user.save()

    logger.info(
        "Customer location updated for telegram_id=%s lat=%s lon=%s",
        telegram_user.telegram_id,
        telegram_user.customer_latitude,
        telegram_user.customer_longitude,
    )

    return Response(
        {
            "success": True,
            "has_customer_location": telegram_user.has_customer_location,
        },
        status=status.HTTP_200_OK,
    )


def sync_telegram_user(miniapp_user) -> TelegramUser:
    telegram_user, _ = TelegramUser.objects.update_or_create(
        telegram_id=miniapp_user.telegram_id,
        defaults={
            "telegram_username": miniapp_user.username,
            "first_name": miniapp_user.first_name,
            "last_name": miniapp_user.last_name,
        },
    )
    return telegram_user


def sync_django_auth_user(telegram_user: TelegramUser) -> User:
    username = build_django_username(telegram_user.telegram_id)

    django_user, _ = User.objects.update_or_create(
        username=username,
        defaults={
            "first_name": telegram_user.first_name[:150],
            "last_name": telegram_user.last_name[:150],
            "is_active": not telegram_user.is_banned,
        },
    )

    django_user.set_unusable_password()
    django_user.save(
        update_fields=[
            "password",
            "first_name",
            "last_name",
            "is_active",
        ]
    )

    return django_user


def get_telegram_user_from_auth_user(user: User) -> TelegramUser | None:
    telegram_id = extract_telegram_id_from_django_username(user.username)

    if telegram_id is None:
        return None

    return TelegramUser.objects.filter(telegram_id=telegram_id).first()


def get_service_profile_for_user(telegram_user: TelegramUser) -> ServiceProfile | None:
    return ServiceProfile.objects.filter(provider=telegram_user).first()


def build_django_username(telegram_id: int) -> str:
    return f"telegram_{telegram_id}"


def extract_telegram_id_from_django_username(username: str) -> int | None:
    prefix = "telegram_"

    if not username.startswith(prefix):
        return None

    raw_telegram_id = username.replace(prefix, "", 1)

    try:
        return int(raw_telegram_id)
    except ValueError:
        return None
