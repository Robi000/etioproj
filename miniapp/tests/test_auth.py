import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from django.test import override_settings

from miniapp.auth import (
    TelegramInitDataValidationError,
    TelegramMiniAppAuthService,
)


TEST_BOT_TOKEN = "123456789:TEST_BOT_TOKEN"


def build_signed_init_data(
    bot_token: str,
    payload: dict[str, str],
) -> str:
    data_check_string = "\n".join(
        f"{key}={payload[key]}"
        for key in sorted(payload.keys())
    )

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

    signed_payload = {
        **payload,
        "hash": calculated_hash,
    }

    return urlencode(signed_payload)


def valid_payload() -> dict[str, str]:
    return {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "auth_date": str(int(time.time())),
        "user": json.dumps(
            {
                "id": 12345,
                "first_name": "Test",
                "last_name": "User",
                "username": "test_user",
                "language_code": "en",
                "allows_write_to_pm": True,
            },
            separators=(",", ":"),
        ),
    }


@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_valid_init_data_returns_structured_user():
    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=valid_payload(),
    )

    result = TelegramMiniAppAuthService.validate_init_data(init_data)

    assert result.user.telegram_id == 12345
    assert result.user.first_name == "Test"
    assert result.user.last_name == "User"
    assert result.user.username == "test_user"
    assert result.user.language_code == "en"
    assert result.user.allows_write_to_pm is True
    assert result.query_id == "AAHdF6IQAAAAAN0XohDhrOrc"


@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_invalid_hash_is_rejected():
    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=valid_payload(),
    )

    tampered_init_data = init_data.replace("Test", "Fake")

    with pytest.raises(TelegramInitDataValidationError):
        TelegramMiniAppAuthService.validate_init_data(tampered_init_data)


@override_settings(TELEGRAM_BOT_TOKEN="")
def test_missing_bot_token_is_rejected():
    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=valid_payload(),
    )

    with pytest.raises(TelegramInitDataValidationError):
        TelegramMiniAppAuthService.validate_init_data(init_data)


@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_malformed_payload_is_rejected():
    with pytest.raises(TelegramInitDataValidationError):
        TelegramMiniAppAuthService.validate_init_data("not-a-valid-query-string")


@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_missing_hash_is_rejected():
    init_data = urlencode(valid_payload())

    with pytest.raises(TelegramInitDataValidationError):
        TelegramMiniAppAuthService.validate_init_data(init_data)


@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_expired_init_data_is_rejected():
    payload = valid_payload()
    payload["auth_date"] = str(int(time.time()) - 90000)

    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=payload,
    )

    with pytest.raises(TelegramInitDataValidationError):
        TelegramMiniAppAuthService.validate_init_data(init_data)


@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_future_auth_date_is_rejected():
    payload = valid_payload()
    payload["auth_date"] = str(int(time.time()) + 120)

    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=payload,
    )

    with pytest.raises(TelegramInitDataValidationError):
        TelegramMiniAppAuthService.validate_init_data(init_data)


@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_missing_user_is_rejected():
    payload = valid_payload()
    del payload["user"]

    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=payload,
    )

    with pytest.raises(TelegramInitDataValidationError):
        TelegramMiniAppAuthService.validate_init_data(init_data)