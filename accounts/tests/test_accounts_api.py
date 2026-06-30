import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from django.test import override_settings
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser


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
                "id": 22222,
                "first_name": "Mini",
                "last_name": "User",
                "username": "mini_user",
                "language_code": "en",
                "allows_write_to_pm": True,
            },
            separators=(",", ":"),
        ),
    }


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_telegram_auth_success_creates_user_and_token(api_client):
    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=valid_payload(),
    )

    response = api_client.post(
        "/api/auth/telegram/",
        {
            "init_data": init_data,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["token"]

    telegram_user = TelegramUser.objects.get(telegram_id=22222)

    assert telegram_user.first_name == "Mini"
    assert telegram_user.last_name == "User"
    assert telegram_user.telegram_username == "mini_user"
    assert Token.objects.count() == 1


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_telegram_auth_invalid_hash_is_rejected(api_client):
    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=valid_payload(),
    )

    tampered_init_data = init_data.replace("Mini", "Fake")

    response = api_client.post(
        "/api/auth/telegram/",
        {
            "init_data": tampered_init_data,
        },
        format="json",
    )

    assert response.status_code == 401
    assert response.data["success"] is False
    assert TelegramUser.objects.count() == 0


@pytest.mark.django_db
def test_telegram_auth_missing_init_data_is_rejected(api_client):
    response = api_client.post(
        "/api/auth/telegram/",
        {},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_me_requires_authentication(api_client):
    response = api_client.get("/api/me/")

    assert response.status_code in (401, 403)


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_me_returns_authenticated_telegram_user(api_client):
    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=valid_payload(),
    )

    auth_response = api_client.post(
        "/api/auth/telegram/",
        {
            "init_data": init_data,
        },
        format="json",
    )

    token = auth_response.data["token"]

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {token}"
    )

    response = api_client.get("/api/me/")

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["user"]["telegram_id"] == 22222
    assert response.data["user"]["telegram_username"] == "mini_user"


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN=TEST_BOT_TOKEN)
def test_accounts_nested_auth_route_also_works(api_client):
    init_data = build_signed_init_data(
        bot_token=TEST_BOT_TOKEN,
        payload=valid_payload(),
    )

    response = api_client.post(
        "/api/accounts/auth/telegram/",
        {
            "init_data": init_data,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["user"]["telegram_id"] == 22222