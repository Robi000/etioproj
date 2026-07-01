import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import TelegramUser
from bot.models import BotRegistrationSession
from services.models import ServiceCategory, ServicePhoto, ServicePrice, ServiceProfile

logger = logging.getLogger("marketplace")

COORDINATE_QUANT = Decimal("0.000001")
PRICE_QUANT = Decimal("0.01")


@dataclass(frozen=True)
class RegistrationSubmitResult:
    success: bool
    message: str
    service_id: int | None = None


class BotRegistrationSubmitter:
    @staticmethod
    def submit(session: BotRegistrationSession) -> RegistrationSubmitResult:
        data = session.data

        valid, message = BotRegistrationSubmitter.validate_session_data(data)
        if not valid:
            return RegistrationSubmitResult(
                success=False,
                message=message,
            )

        try:
            with transaction.atomic():
                existing_service = ServiceProfile.objects.filter(
                    provider__telegram_id=session.telegram_user_id,
                ).first()
                if existing_service is not None:
                    logger.info(
                        "event=bot_registration_duplicate_service telegram_user_id=%s service_id=%s",
                        session.telegram_user_id,
                        existing_service.id,
                    )
                    return RegistrationSubmitResult(
                        success=False,
                        message=(
                            "⚠️ You already have a service profile. "
                            "Only one service is allowed per provider."
                        ),
                        service_id=existing_service.id,
                    )

                telegram_user = BotRegistrationSubmitter.create_or_update_user(session, data)
                category = BotRegistrationSubmitter.get_or_create_category(data["category"])
                service = BotRegistrationSubmitter.create_pending_service(
                    telegram_user=telegram_user,
                    category=category,
                    data=data,
                )

                BotRegistrationSubmitter.create_prices(service, data.get("prices", {}))
                BotRegistrationSubmitter.create_photos(service, data.get("photos", []))

                completed_data = dict(session.data)
                completed_data["submitted_service_id"] = service.id

                session.data = completed_data
                session.state = BotRegistrationSession.State.COMPLETED
                session.save(update_fields=["data", "state", "updated_at"])

                logger.info(
                    "event=bot_registration_submitted telegram_user_id=%s service_id=%s",
                    session.telegram_user_id,
                    service.id,
                )

                return RegistrationSubmitResult(
                    success=True,
                    message=(
                        "🎉 Registration completed and submitted successfully.\n\n"
                        "Your service is now pending admin approval."
                    ),
                    service_id=service.id,
                )

        except (ValueError, ValidationError):
            logger.exception(
                "event=bot_registration_submit_validation_failed telegram_user_id=%s",
                session.telegram_user_id,
            )
            return RegistrationSubmitResult(
                success=False,
                message="⚠️ Registration draft has invalid data. Please review it and try again.",
            )

        except Exception:
            logger.exception(
                "event=bot_registration_submit_failed telegram_user_id=%s",
                session.telegram_user_id,
            )
            return RegistrationSubmitResult(
                success=False,
                message="⚠️ Registration could not be submitted. Please try again.",
            )

    @staticmethod
    def validate_session_data(data: dict[str, Any]) -> tuple[bool, str]:
        required_fields = [
            "role",
            "telegram_username",
            "phone_number",
            "category",
            "title",
            "description",
            "location",
            "prices",
            "photos",
        ]

        for field in required_fields:
            if not data.get(field):
                return False, f"⚠️ Missing required field: {field}"

        if data["role"] not in {
            TelegramUser.Role.PROVIDER,
            TelegramUser.Role.BOTH,
            TelegramUser.Role.ADMIN,
        }:
            return False, "⚠️ Only providers can submit a service registration."

        location = data.get("location", {})

        if location.get("source") != "gps":
            return False, "⚠️ GPS location is required."

        if location.get("latitude") is None or location.get("longitude") is None:
            return False, "⚠️ GPS latitude and longitude are required."

        try:
            latitude = BotRegistrationSubmitter.normalize_coordinate(location["latitude"])
            longitude = BotRegistrationSubmitter.normalize_coordinate(location["longitude"])
        except ValueError:
            return False, "⚠️ GPS latitude and longitude must be valid numbers."

        if latitude < Decimal("-90") or latitude > Decimal("90"):
            return False, "⚠️ GPS latitude must be between -90 and 90."

        if longitude < Decimal("-180") or longitude > Decimal("180"):
            return False, "⚠️ GPS longitude must be between -180 and 180."

        prices = data.get("prices", {})

        if not prices:
            return False, "⚠️ At least one price is required."

        for price_type, amount in prices.items():
            if price_type not in {
                ServicePrice.PriceType.HALF_DAY,
                ServicePrice.PriceType.FULL_DAY,
                ServicePrice.PriceType.NIGHT,
            }:
                return False, f"⚠️ Invalid price type: {price_type}"

            try:
                if BotRegistrationSubmitter.normalize_price(amount) <= Decimal("0"):
                    return False, "⚠️ Prices must be greater than zero."
            except ValueError:
                return False, "⚠️ Price amount must be a valid number."

        photos = data.get("photos", [])

        if len(photos) < 1:
            return False, "⚠️ At least one photo is required."

        if len(photos) > 3:
            return False, "⚠️ Maximum 3 photos allowed."

        return True, "Ready."

    @staticmethod
    def create_or_update_user(
        session: BotRegistrationSession,
        data: dict[str, Any],
    ) -> TelegramUser:
        telegram_user, _ = TelegramUser.objects.get_or_create(
            telegram_id=session.telegram_user_id,
            defaults={
                "telegram_username": data["telegram_username"],
                "phone_number": data["phone_number"],
                "secondary_phone_number": data.get("secondary_phone_number", ""),
                "role": data["role"],
                "city": session.city,
            },
        )

        telegram_user.telegram_username = data["telegram_username"]
        telegram_user.phone_number = data["phone_number"]
        telegram_user.secondary_phone_number = data.get("secondary_phone_number", "")
        telegram_user.role = data["role"]
        telegram_user.city = session.city
        telegram_user.save(
            update_fields=[
                "telegram_username",
                "phone_number",
                "secondary_phone_number",
                "role",
                "city",
                "updated_at",
            ]
        )

        return telegram_user

    @staticmethod
    def get_or_create_category(category_name: str) -> ServiceCategory:
        category, _ = ServiceCategory.objects.get_or_create(
            name=category_name,
            defaults={
                "active": True,
            },
        )

        if not category.active:
            category.active = True
            category.save(update_fields=["active", "updated_at"])

        return category

    @staticmethod
    def create_pending_service(
        telegram_user: TelegramUser,
        category: ServiceCategory,
        data: dict[str, Any],
    ) -> ServiceProfile:
        location = data["location"]
        latitude = BotRegistrationSubmitter.normalize_coordinate(location["latitude"])
        longitude = BotRegistrationSubmitter.normalize_coordinate(location["longitude"])

        return ServiceProfile.objects.create(
            provider=telegram_user,
            category=category,
            title=str(data["title"]),
            description=data["description"],
            latitude=latitude,
            longitude=longitude,
            city_text=location.get("city_text", ""),
            location_source=ServiceProfile.LocationSource.GPS,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
            approval_status=ServiceProfile.ApprovalStatus.PENDING,
        )

    @staticmethod
    def create_prices(
        service: ServiceProfile,
        prices: dict[str, Any],
    ) -> None:
        for price_type, amount in prices.items():
            ServicePrice.objects.create(
                service=service,
                price_type=price_type,
                amount=BotRegistrationSubmitter.normalize_price(amount),
            )

    @staticmethod
    def create_photos(
        service: ServiceProfile,
        photos: list[dict[str, Any]],
    ) -> None:
        for index, photo in enumerate(photos, start=1):
            sp = ServicePhoto.objects.create(
                service=service,
                telegram_file_id=photo["telegram_file_id"],
                order_index=index,
            )
            from services.photo_storage import store_photo_locally
            store_photo_locally(sp)

    @staticmethod
    def normalize_coordinate(value: Any) -> Decimal:
        try:
            return Decimal(str(value)).quantize(
                COORDINATE_QUANT,
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Coordinate must be a valid decimal number.") from exc

    @staticmethod
    def normalize_price(value: Any) -> Decimal:
        try:
            return Decimal(str(value)).quantize(
                PRICE_QUANT,
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Price must be a valid decimal number.") from exc
