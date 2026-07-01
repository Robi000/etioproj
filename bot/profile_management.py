from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from accounts.models import TelegramUser
from bot.models import BotRegistrationSession
from services.models import PhotoChangeRequest, ServiceCategory, ServicePhoto, ServicePrice, ServiceProfile


PROFILE_MENU_TEXTS = {
    "my profile",
    "profile",
    "/profile",
}
EDIT_PROFILE_TEXTS = {
    "edit profile",
    "edit",
    "/edit",
}
GO_OFFLINE_TEXTS = {
    "go offline",
    "offline",
    "/offline",
}
GO_ONLINE_TEXTS = {
    "go online",
    "online",
    "/online",
}

PROFILE_EDIT_PREFIX = "profile_edit:"
PROFILE_PRICE_PREFIX = "profile_price:"
MIN_PROVIDER_AGE = 18

OFFLINE_WARNING_TEXT = (
    "🟥🟥🟥 YOU ARE OFFLINE 🟥🟥🟥\n\n"
    "Your provider profile is NOT visible to customers right now.\n"
    "You will not appear in swipe discovery.\n"
    "You will not appear in grid discovery.\n"
    "Customers cannot discover this service while visibility is OFF.\n\n"
    "To become visible again, tap the bottom button: Go Online."
)


def normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def is_profile_text_command(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in (
        PROFILE_MENU_TEXTS
        | EDIT_PROFILE_TEXTS
        | GO_OFFLINE_TEXTS
        | GO_ONLINE_TEXTS
    )


def is_go_online_text(text: str) -> bool:
    return normalize_text(text) in GO_ONLINE_TEXTS


def is_go_offline_text(text: str) -> bool:
    return normalize_text(text) in GO_OFFLINE_TEXTS


def is_my_profile_text(text: str) -> bool:
    return normalize_text(text) in PROFILE_MENU_TEXTS


def is_edit_profile_text(text: str) -> bool:
    return normalize_text(text) in EDIT_PROFILE_TEXTS


def get_provider_service(telegram_user_id: int | None) -> ServiceProfile | None:
    if telegram_user_id is None:
        return None

    return (
        ServiceProfile.objects.select_related("provider", "category", "approved_by")
        .prefetch_related("prices", "photos")
        .filter(provider__telegram_id=telegram_user_id)
        .first()
    )


def service_is_offline(telegram_user_id: int | None) -> bool:
    service = get_provider_service(telegram_user_id)
    return bool(
        service
        and service.visibility_status == ServiceProfile.VisibilityStatus.OFF
    )


def build_price_map(service: ServiceProfile) -> dict[str, str]:
    return {
        price.price_type: str(price.amount)
        for price in service.prices.all()
    }


def build_profile_text(service: ServiceProfile | None) -> str:
    if service is None:
        return (
            "📋 My Profile\n\n"
            "No provider profile was found yet.\n"
            "Use /start, then press Create Service to register."
        )

    provider = service.provider
    prices = build_price_map(service)
    price_lines = []
    for key, label in {
        ServicePrice.PriceType.HALF_DAY: "Half-Day",
        ServicePrice.PriceType.FULL_DAY: "Full-Day",
        ServicePrice.PriceType.NIGHT: "Night",
    }.items():
        value = prices.get(key)
        if value:
            price_lines.append(f"{label}: {value}")

    price_text = "\n".join(price_lines) if price_lines else "No prices set"
    visibility = (
        "ON - visible to customers"
        if service.visibility_status == ServiceProfile.VisibilityStatus.ON
        else "OFF - hidden from customers"
    )

    return (
        "📋 My Provider Profile\n\n"
        f"Account: @{provider.telegram_username or 'no_username'}\n"
        f"Telegram ID: {provider.telegram_id}\n"
        f"Primary Phone: {provider.phone_number or 'Not set'}\n"
        f"Secondary Phone: {provider.secondary_phone_number or 'Not set'}\n\n"
        f"Category: {service.category.name}\n"
        f"Age: {service.title}\n"
        f"Description: {service.description}\n"
        f"Application Status: {service.approval_status}\n"
        f"Visibility: {visibility}\n"
        f"Location Source: {service.location_source}\n"
        f"GPS: {service.latitude}, {service.longitude}\n\n"
        f"Prices:\n{price_text}\n\n"
        f"Photos: {service.photos.count()}/3"
    )


def build_delete_preview_text(service: ServiceProfile | None) -> str:
    if service is None:
        return "No provider profile was found to delete."

    return (
        "⚠️ Delete Provider Profile?\n\n"
        "This will delete the provider service application/profile, prices, and photo references.\n"
        "Photos are not displayed here, but their Telegram file IDs will be removed from this service.\n\n"
        f"Account: @{service.provider.telegram_username or 'no_username'}\n"
        f"Telegram ID: {service.provider.telegram_id}\n"
        f"Service ID: {service.id}\n"
        f"Category: {service.category.name}\n"
        f"Age: {service.title}\n"
        f"Status: {service.approval_status}\n"
        f"Visibility: {service.visibility_status}\n"
        f"Prices: {service.prices.count()}\n"
        f"Photos: {service.photos.count()}/3\n\n"
        "Confirm only if this is the exact profile you want to remove."
    )


def delete_provider_profile(telegram_user_id: int) -> bool:
    with transaction.atomic():
        service = get_provider_service(telegram_user_id)
        if service is None:
            return False

        service.delete()
        BotRegistrationSession.objects.filter(
            telegram_user_id=telegram_user_id,
        ).delete()
        return True


def set_visibility(telegram_user_id: int, visibility: str) -> ServiceProfile | None:
    service = get_provider_service(telegram_user_id)
    if service is None:
        return None

    service.visibility_status = visibility
    service.save(update_fields=["visibility_status", "updated_at"])
    sync_session_from_service(service)
    return service


def get_or_create_profile_edit_session(
    telegram_user_id: int,
    chat_id: int,
) -> BotRegistrationSession:
    service = get_provider_service(telegram_user_id)
    data = build_session_data_from_service(service) if service else {}

    session, _ = BotRegistrationSession.objects.update_or_create(
        telegram_user_id=telegram_user_id,
        defaults={
            "chat_id": chat_id,
            "state": BotRegistrationSession.State.COMPLETED,
            "data": data,
        },
    )
    return session


def set_profile_edit_state(
    telegram_user_id: int,
    chat_id: int,
    state: str,
) -> BotRegistrationSession:
    session = get_or_create_profile_edit_session(telegram_user_id, chat_id)
    session.state = state
    session.save(update_fields=["state", "updated_at"])
    return session


def clear_profile_edit_state(telegram_user_id: int) -> None:
    session = BotRegistrationSession.objects.filter(
        telegram_user_id=telegram_user_id,
    ).first()
    if session is None:
        return

    session.state = BotRegistrationSession.State.COMPLETED
    session.save(update_fields=["state", "updated_at"])


def build_session_data_from_service(service: ServiceProfile | None) -> dict[str, Any]:
    if service is None:
        return {}

    provider = service.provider
    return {
        "role": provider.role,
        "telegram_username": provider.telegram_username,
        "phone_number": provider.phone_number,
        "secondary_phone_number": provider.secondary_phone_number or "",
        "category": service.category.name,
        "title": service.title,
        "description": service.description,
        "location": {
            "source": service.location_source,
            "city_text": service.city_text,
            "latitude": str(service.latitude) if service.latitude is not None else None,
            "longitude": str(service.longitude) if service.longitude is not None else None,
        },
        "prices": build_price_map(service),
        "photos": list(
            service.photos.order_by("order_index").values(
                "telegram_file_id",
                "order_index",
            )
        ),
        "submitted_service_id": service.id,
    }


def sync_session_from_service(service: ServiceProfile) -> None:
    BotRegistrationSession.objects.update_or_create(
        telegram_user_id=service.provider.telegram_id,
        defaults={
            "chat_id": service.provider.telegram_id,
            "state": BotRegistrationSession.State.COMPLETED,
            "data": build_session_data_from_service(service),
        },
    )


def update_category(telegram_user_id: int, category_name: str) -> ServiceProfile | None:
    service = get_provider_service(telegram_user_id)
    if service is None:
        return None

    category, _ = ServiceCategory.objects.get_or_create(
        name=category_name,
        defaults={"active": True},
    )
    service.category = category
    service.save(update_fields=["category", "updated_at"])
    sync_session_from_service(service)
    return service


def update_age(telegram_user_id: int, age_text: str) -> tuple[bool, str]:
    cleaned = age_text.strip()
    if not cleaned.isdigit():
        return False, "Age must be a number only."

    age = int(cleaned)
    if age < MIN_PROVIDER_AGE:
        return False, "Provider profiles are only available for people 18 or older."
    if age > 120:
        return False, "Please enter a valid age between 18 and 120."

    service = get_provider_service(telegram_user_id)
    if service is None:
        return False, "No provider profile was found."

    service.title = str(age)
    service.save(update_fields=["title", "updated_at"])
    sync_session_from_service(service)
    return True, "Age updated."


def update_description(telegram_user_id: int, description: str) -> tuple[bool, str]:
    cleaned = description.strip()
    if len(cleaned) < 10 or len(cleaned) > 30:
        return False, "Description must be between 10 and 30 characters."

    service = get_provider_service(telegram_user_id)
    if service is None:
        return False, "No provider profile was found."

    service.description = cleaned
    service.save(update_fields=["description", "updated_at"])
    sync_session_from_service(service)
    return True, "Description updated."


def update_phone(
    telegram_user_id: int,
    phone: str,
    secondary: bool = False,
) -> tuple[bool, str]:
    service = get_provider_service(telegram_user_id)
    if service is None:
        return False, "No provider profile was found."

    cleaned = phone.strip()
    if secondary and normalize_text(cleaned) in {"skip", "none", "remove"}:
        cleaned = ""
    elif not cleaned or not cleaned_phone_is_valid(cleaned):
        return False, "Send a valid phone number using digits, spaces, +, -, or brackets."

    provider = service.provider
    if secondary:
        provider.secondary_phone_number = cleaned
        field = "secondary_phone_number"
        message = "Secondary phone updated."
    else:
        provider.phone_number = cleaned
        field = "phone_number"
        message = "Primary phone updated."

    provider.save(update_fields=[field, "updated_at"])
    sync_session_from_service(service)
    return True, message


def cleaned_phone_is_valid(phone: str) -> bool:
    allowed = set("0123456789 +-()")
    digits = [character for character in phone if character.isdigit()]
    return all(character in allowed for character in phone) and len(digits) >= 7


def update_location_from_gps(
    telegram_user_id: int,
    location: dict[str, Any],
) -> tuple[bool, str]:
    service = get_provider_service(telegram_user_id)
    if service is None:
        return False, "No provider profile was found."

    try:
        latitude = Decimal(str(location.get("latitude")))
        longitude = Decimal(str(location.get("longitude")))
    except (InvalidOperation, TypeError, ValueError):
        return False, "GPS latitude and longitude must be valid numbers."

    if latitude < Decimal("-90") or latitude > Decimal("90"):
        return False, "Latitude must be between -90 and 90."
    if longitude < Decimal("-180") or longitude > Decimal("180"):
        return False, "Longitude must be between -180 and 180."

    from services.models import CityLocation
    city_name = CityLocation.get_city_for_coordinates(longitude, latitude) or ""

    service.latitude = latitude
    service.longitude = longitude
    service.city_text = city_name
    service.location_source = ServiceProfile.LocationSource.GPS
    service.save(update_fields=["latitude", "longitude", "city_text", "location_source", "updated_at"])

    provider = service.provider
    provider.city = city_name
    provider.save(update_fields=["city", "updated_at"])

    sync_session_from_service(service)
    return True, "GPS location updated."


def update_price(
    telegram_user_id: int,
    price_type: str,
    amount_text: str,
) -> tuple[bool, str]:
    service = get_provider_service(telegram_user_id)
    if service is None:
        return False, "No provider profile was found."

    if price_type not in {
        ServicePrice.PriceType.HALF_DAY,
        ServicePrice.PriceType.FULL_DAY,
        ServicePrice.PriceType.NIGHT,
    }:
        return False, "Invalid price type."

    try:
        amount = Decimal(amount_text.strip())
    except (InvalidOperation, AttributeError):
        return False, "Send a valid price number."

    if amount <= Decimal("0"):
        return False, "Price must be greater than zero."

    ServicePrice.objects.update_or_create(
        service=service,
        price_type=price_type,
        defaults={"amount": amount},
    )
    sync_session_from_service(service)
    return True, "Price updated."


def add_photo(
    telegram_user_id: int,
    file_id: str,
) -> tuple[bool, str]:
    service = get_provider_service(telegram_user_id)
    if service is None:
        return False, "No provider profile was found."

    if not file_id:
        return False, "Photo file ID was not received."

    used_indexes = set(service.photos.values_list("order_index", flat=True))

    if service.approval_status == ServiceProfile.ApprovalStatus.APPROVED:
        order_index = next((index for index in range(1, 4) if index not in used_indexes), 3)
        change = PhotoChangeRequest.objects.create(
            service=service,
            new_file_id=file_id,
            order_index=order_index,
        )
        from bot.service_notifications import queue_photo_change_admin_notification
        queue_photo_change_admin_notification(change.id)
        return True, (
            "📸 Your photo change request has been submitted for admin review. "
            "It will be applied after approval."
        )
    else:
        if not service.can_add_photo():
            return False, "Maximum 3 photos allowed."
        order_index = next((index for index in range(1, 4) if index not in used_indexes), 3)
        photo = ServicePhoto.objects.create(
            service=service,
            telegram_file_id=file_id,
            order_index=order_index,
        )
        from services.photo_storage import store_photo_locally
        store_photo_locally(photo)
        sync_session_from_service(service)
        return True, f"Photo {service.photos.count()}/3 saved."
