import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from django.conf import settings

logger = logging.getLogger("marketplace")


class TelegramInitDataValidationError(Exception):
    """
    Raised when Telegram Mini App initData cannot be trusted.
    """


@dataclass(frozen=True)
class TelegramMiniAppUser:
    telegram_id: int
    first_name: str
    last_name: str
    username: str
    language_code: str
    allows_write_to_pm: bool


@dataclass(frozen=True)
class TelegramInitDataResult:
    user: TelegramMiniAppUser
    auth_date: int
    query_id: str
    raw_data: dict[str, str]


class TelegramMiniAppAuthService:
    """
    Validates Telegram Mini App WebApp initData.

    The service verifies:
    - bot token exists
    - payload is parseable
    - hash exists
    - auth_date exists
    - auth_date is not expired
    - user object exists
    - computed hash matches Telegram hash
    """

    DEFAULT_MAX_AGE_SECONDS = 86400

    @classmethod
    def validate_init_data(
        cls,
        init_data: str,
        max_age_seconds: int | None = None,
    ) -> TelegramInitDataResult:
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN is missing while validating Mini App initData.")
            raise TelegramInitDataValidationError("Telegram bot token is not configured.")

        if not init_data or not init_data.strip():
            raise TelegramInitDataValidationError("Telegram initData is required.")

        parsed_data = cls._parse_init_data(init_data)
        received_hash = parsed_data.get("hash")

        if not received_hash:
            raise TelegramInitDataValidationError("Telegram initData hash is missing.")

        auth_date = cls._extract_auth_date(parsed_data)
        cls._validate_auth_date(
            auth_date=auth_date,
            max_age_seconds=max_age_seconds or cls.DEFAULT_MAX_AGE_SECONDS,
        )

        cls._validate_hash(
            parsed_data=parsed_data,
            received_hash=received_hash,
            bot_token=settings.TELEGRAM_BOT_TOKEN,
        )

        user = cls._extract_user(parsed_data)

        return TelegramInitDataResult(
            user=user,
            auth_date=auth_date,
            query_id=parsed_data.get("query_id", ""),
            raw_data=parsed_data,
        )

    @classmethod
    def _parse_init_data(cls, init_data: str) -> dict[str, str]:
        try:
            parsed_pairs = parse_qsl(
                init_data,
                keep_blank_values=True,
                strict_parsing=True,
            )
        except ValueError as exc:
            raise TelegramInitDataValidationError("Telegram initData is malformed.") from exc

        parsed_data: dict[str, str] = {}

        for key, value in parsed_pairs:
            if key in parsed_data:
                raise TelegramInitDataValidationError(
                    f"Telegram initData contains duplicate key: {key}"
                )

            parsed_data[key] = value

        return parsed_data

    @classmethod
    def _extract_auth_date(cls, parsed_data: dict[str, str]) -> int:
        auth_date_value = parsed_data.get("auth_date")

        if not auth_date_value:
            raise TelegramInitDataValidationError("Telegram initData auth_date is missing.")

        try:
            return int(auth_date_value)
        except ValueError as exc:
            raise TelegramInitDataValidationError("Telegram initData auth_date is invalid.") from exc

    @classmethod
    def _validate_auth_date(
        cls,
        auth_date: int,
        max_age_seconds: int,
    ) -> None:
        current_time = int(time.time())

        if auth_date > current_time + 60:
            raise TelegramInitDataValidationError("Telegram initData auth_date is from the future.")

        if current_time - auth_date > max_age_seconds:
            raise TelegramInitDataValidationError("Telegram initData has expired.")

    @classmethod
    def _validate_hash(
        cls,
        parsed_data: dict[str, str],
        received_hash: str,
        bot_token: str,
    ) -> None:
        data_check_string = cls._build_data_check_string(parsed_data)

        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.warning("Invalid Telegram Mini App initData hash.")
            raise TelegramInitDataValidationError("Telegram initData hash is invalid.")

    @classmethod
    def _build_data_check_string(cls, parsed_data: dict[str, str]) -> str:
        check_items = []

        for key in sorted(parsed_data.keys()):
            if key == "hash":
                continue

            check_items.append(f"{key}={parsed_data[key]}")

        return "\n".join(check_items)

    @classmethod
    def _extract_user(cls, parsed_data: dict[str, str]) -> TelegramMiniAppUser:
        user_json = parsed_data.get("user")

        if not user_json:
            raise TelegramInitDataValidationError("Telegram initData user is missing.")

        try:
            user_data: dict[str, Any] = json.loads(user_json)
        except json.JSONDecodeError as exc:
            raise TelegramInitDataValidationError("Telegram initData user JSON is invalid.") from exc

        telegram_id = user_data.get("id")

        if not isinstance(telegram_id, int):
            raise TelegramInitDataValidationError("Telegram user id is missing or invalid.")

        return TelegramMiniAppUser(
            telegram_id=telegram_id,
            first_name=str(user_data.get("first_name", "")),
            last_name=str(user_data.get("last_name", "")),
            username=str(user_data.get("username", "")),
            language_code=str(user_data.get("language_code", "")),
            allows_write_to_pm=bool(user_data.get("allows_write_to_pm", False)),
        )