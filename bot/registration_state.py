import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from bot.models import BotRegistrationSession

logger = logging.getLogger("marketplace")

ROLE_PROVIDER = "provider"
ROLE_CUSTOMER = "customer"
ROLE_BOTH = "both"
MIN_PROVIDER_AGE = 18

PRICE_TYPES = {
    "half_day": "Half-Day",
    "full_day": "Full-Day",
    "night": "Night",
}

ALLOWED_CATEGORIES = {
    "Electrician",
    "Cleaner",
    "Tutor",
    "Mechanic",
    "Plumber",
}


class RegistrationStateMachine:
    @staticmethod
    def start_or_reset(
        telegram_user_id: int,
        chat_id: int,
        telegram_username: str = "",
    ) -> BotRegistrationSession:
        session, _ = BotRegistrationSession.objects.update_or_create(
            telegram_user_id=telegram_user_id,
            defaults={
                "chat_id": chat_id,
                "state": BotRegistrationSession.State.SELECT_ROLE,
                "data": {
                    "role": "",
                    "phone_number": "",
                    "secondary_phone_number": "",
                    "telegram_username": telegram_username,
                    "category": "",
                    "title": "",
                    "description": "",
                    "location": {},
                    "prices": {},
                    "photos": [],
                },
            },
        )
        logger.info(
            "event=bot_registration_started telegram_user_id=%s chat_id=%s username_present=%s",
            telegram_user_id,
            chat_id,
            bool(telegram_username),
        )
        return session

    @staticmethod
    def get_session(telegram_user_id: int) -> BotRegistrationSession | None:
        return BotRegistrationSession.objects.filter(
            telegram_user_id=telegram_user_id,
        ).first()

    @staticmethod
    def cancel(telegram_user_id: int) -> BotRegistrationSession | None:
        session = RegistrationStateMachine.get_session(telegram_user_id)
        if session is None:
            return None

        session.state = BotRegistrationSession.State.CANCELLED
        session.save(update_fields=["state", "updated_at"])
        logger.info(
            "event=bot_registration_cancelled telegram_user_id=%s",
            telegram_user_id,
        )
        return session

    @staticmethod
    def set_role(
        session: BotRegistrationSession,
        role: str,
    ) -> tuple[bool, str]:
        if role not in {ROLE_PROVIDER, ROLE_CUSTOMER, ROLE_BOTH}:
            return False, "⚠️ Please select a valid role from the buttons."

        data = session.data
        data["role"] = role
        session.data = data

        if role == ROLE_CUSTOMER:
            session.state = BotRegistrationSession.State.CATEGORY
        else:
            session.state = BotRegistrationSession.State.PROVIDER_PHONE

        session.save(update_fields=["data", "state", "updated_at"])
        return True, "✅ Role saved."

    @staticmethod
    def set_phone_from_contact(
        session: BotRegistrationSession,
        contact: dict[str, Any],
    ) -> tuple[bool, str]:
        phone_number = str(contact.get("phone_number", "")).strip()

        if not phone_number:
            return False, "⚠️ Phone number was not received. Please use the share phone button."

        data = session.data
        data["phone_number"] = phone_number
        session.data = data
        session.state = BotRegistrationSession.State.SECONDARY_PHONE
        session.save(update_fields=["data", "state", "updated_at"])
        return True, "✅ Primary phone saved."

    @staticmethod
    def set_secondary_phone_number(
        session: BotRegistrationSession,
        phone_number: str,
    ) -> tuple[bool, str]:
        cleaned = phone_number.strip()

        if cleaned.lower() in {"skip", "no", "none", "skip secondary phone"}:
            data = session.data
            data["secondary_phone_number"] = ""
            session.data = data
            session.state = BotRegistrationSession.State.CATEGORY
            session.save(update_fields=["data", "state", "updated_at"])
            return True, "✅ Secondary phone skipped."

        if not re.match(r"^[\d\s\+\-\(\)]{1,32}$", cleaned):
            return False, "⚠️ Secondary phone can contain only digits, spaces, +, -, or brackets."

        digits_only = re.sub(r"[\s\+\-\(\)]", "", cleaned)

        if len(digits_only) < 7:
            return False, "⚠️ Secondary phone must have at least 7 digits."

        data = session.data
        data["secondary_phone_number"] = cleaned
        session.data = data
        session.state = BotRegistrationSession.State.CATEGORY
        session.save(update_fields=["data", "state", "updated_at"])

        return True, "✅ Secondary phone saved."

    @staticmethod
    def set_category(
        session: BotRegistrationSession,
        category: str,
    ) -> tuple[bool, str]:
        cleaned = " ".join(category.strip().split())

        if cleaned not in ALLOWED_CATEGORIES:
            return False, "⚠️ Please select one of the category buttons."

        data = session.data
        data["category"] = cleaned
        session.data = data
        session.state = BotRegistrationSession.State.TITLE
        session.save(update_fields=["data", "state", "updated_at"])
        return True, f"✅ Category saved: {cleaned}."

    @staticmethod
    def set_title(
        session: BotRegistrationSession,
        title: str,
    ) -> tuple[bool, str]:
        cleaned = title.strip()

        if not cleaned.isdigit():
            return False, "⚠️ Age must be a number only."

        age = int(cleaned)

        if age < MIN_PROVIDER_AGE:
            session.state = BotRegistrationSession.State.CANCELLED
            session.data = {
                "underage_rejected": True,
            }
            session.save(update_fields=["data", "state", "updated_at"])
            logger.info(
                "event=bot_registration_underage_rejected telegram_user_id=%s age=%s",
                session.telegram_user_id,
                age,
            )
            return False, "🚫 Registration stopped. Provider registration is only for people 18 or older. Your saved draft was removed."

        if age > 120:
            return False, "⚠️ Please enter a valid age between 18 and 120."

        data = session.data
        data["title"] = str(age)
        session.data = data
        session.state = BotRegistrationSession.State.DESCRIPTION
        session.save(update_fields=["data", "state", "updated_at"])

        return True, "✅ Age saved."

    @staticmethod
    def set_description(
        session: BotRegistrationSession,
        description: str,
    ) -> tuple[bool, str]:
        cleaned = description.strip()

        if len(cleaned) < 10:
            return False, "⚠️ Description is too short. Please send at least 10 characters."

        data = session.data
        data["description"] = cleaned
        session.data = data
        session.state = BotRegistrationSession.State.LOCATION
        session.save(update_fields=["data", "state", "updated_at"])
        return True, "✅ Description saved."

    @staticmethod
    def set_location_from_text(
        session: BotRegistrationSession,
        city_text: str,
    ) -> tuple[bool, str]:
        return False, "⚠️ Manual city entry is disabled. Please share GPS location."

    @staticmethod
    def set_location_from_gps(
        session: BotRegistrationSession,
        location: dict[str, Any],
    ) -> tuple[bool, str]:
        latitude = location.get("latitude")
        longitude = location.get("longitude")

        if latitude is None or longitude is None:
            return False, "⚠️ GPS location was not received correctly."

        from services.models import CityLocation
        city_name = CityLocation.get_city_for_coordinates(longitude, latitude) or ""
        session.city = city_name

        data = session.data
        data["location"] = {
            "source": "gps",
            "city_text": city_name,
            "latitude": latitude,
            "longitude": longitude,
        }
        session.data = data
        session.state = BotRegistrationSession.State.PRICES
        session.save(update_fields=["data", "state", "city", "updated_at"])
        return True, "✅ GPS location saved."

    @staticmethod
    def set_price(
        session: BotRegistrationSession,
        price_type: str,
        amount_text: str,
    ) -> tuple[bool, str]:
        if price_type not in PRICE_TYPES:
            return False, "⚠️ Invalid price type."

        try:
            amount = Decimal(amount_text.strip())
        except (InvalidOperation, AttributeError):
            return False, "⚠️ Please send a valid number for the price."

        if amount <= Decimal("0"):
            return False, "⚠️ Price must be greater than zero."

        data = session.data
        prices = data.get("prices", {})
        prices[price_type] = str(amount)
        data["prices"] = prices
        session.data = data
        session.save(update_fields=["data", "updated_at"])
        return True, f"✅ {PRICE_TYPES[price_type]} price saved."

    @staticmethod
    def finish_prices(session: BotRegistrationSession) -> tuple[bool, str]:
        prices = session.data.get("prices", {})

        if not prices:
            return False, "⚠️ At least one price is required before continuing."

        session.state = BotRegistrationSession.State.PHOTOS
        session.save(update_fields=["state", "updated_at"])
        return True, "✅ Prices saved."

    @staticmethod
    def add_photo(
        session: BotRegistrationSession,
        file_id: str,
    ) -> tuple[bool, str]:
        if not file_id:
            return False, "⚠️ Photo file ID was not received."

        data = session.data
        photos = data.get("photos", [])

        if len(photos) >= 3:
            return False, "⚠️ Maximum 3 photos allowed."

        photos.append(
            {
                "telegram_file_id": file_id,
                "order_index": len(photos) + 1,
            }
        )
        data["photos"] = photos
        session.data = data
        session.save(update_fields=["data", "updated_at"])
        return True, f"✅ Photo {len(photos)}/3 saved."

    @staticmethod
    def finish_photos(session: BotRegistrationSession) -> tuple[bool, str]:
        photos = session.data.get("photos", [])

        if len(photos) < 1:
            return False, "⚠️ At least one photo is required."

        session.state = BotRegistrationSession.State.SUBMIT
        session.save(update_fields=["state", "updated_at"])
        return True, "✅ Photos saved."

    @staticmethod
    def submit(session: BotRegistrationSession) -> tuple[bool, str]:
        valid, message = RegistrationStateMachine.validate_ready_for_submit(session)
        if not valid:
            return False, message

        from bot.registration_submitter import BotRegistrationSubmitter

        result = BotRegistrationSubmitter.submit(session)

        return result.success, result.message

    @staticmethod
    def validate_ready_for_submit(session: BotRegistrationSession) -> tuple[bool, str]:
        data = session.data

        required_fields = [
            "role",
            "category",
            "title",
            "description",
        ]

        for field in required_fields:
            if not data.get(field):
                return False, f"⚠️ Missing required field: {field}"

        if data.get("role") in {ROLE_PROVIDER, ROLE_BOTH}:
            if not data.get("telegram_username"):
                return False, "⚠️ Telegram username is required for provider registration."

            if not data.get("phone_number"):
                return False, "⚠️ Primary phone number is required."

        if not data.get("location"):
            return False, "⚠️ Location is required."

        if not data.get("prices"):
            return False, "⚠️ At least one price is required."

        if len(data.get("photos", [])) < 1:
            return False, "⚠️ At least one photo is required."

        return True, "✅ Ready."
