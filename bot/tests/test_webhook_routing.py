import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import TelegramUser
from approvals.models import ContactRequest
from bot.handlers import handle_telegram_update
from bot.location import (
    LOCATION_REQUEST_TEXT,
    is_far_from_addis,
    validate_ethiopia_coordinates,
)
from bot.models import BotRegistrationSession
from bot.policy import POLICY_VERSION
from bot.services import TelegramBotService
from services.models import ServiceCategory, ServiceProfile


class FakeTelegramBotService:
    instances: list["FakeTelegramBotService"] = []

    def __init__(self) -> None:
        self.start_menu_chat_ids: list[int] = []
        self.sent_messages: list[dict[str, Any]] = []
        self.answered_callbacks: list[dict[str, str]] = []
        FakeTelegramBotService.instances.append(self)

    def send_start_menu(self, chat_id: int) -> bool:
        self.start_menu_chat_ids.append(chat_id)
        return True

    def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any | None = None,
    ) -> bool:
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )
        return True

    def answer_callback(self, callback_query_id: str, text: str) -> bool:
        self.answered_callbacks.append(
            {
                "callback_query_id": callback_query_id,
                "text": text,
            }
        )
        return True

    def build_mini_app_keyboard(
        self,
        text: str,
        screen: str | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> dict[str, str | None]:
        return {
            "text": text,
            "screen": screen,
            "query_params": query_params or {},
        }

    def build_role_keyboard(self) -> dict[str, str]:
        return {"keyboard": "role"}

    def build_category_keyboard(self) -> dict[str, str]:
        return {"keyboard": "category"}

    def build_customer_category_keyboard(self) -> dict[str, str]:
        return {"keyboard": "customer_category"}

    def build_secondary_phone_keyboard(self) -> dict[str, str]:
        return {"keyboard": "secondary_phone"}

    def build_price_keyboard(self, prices: dict | None = None) -> dict[str, Any]:
        return {
            "keyboard": "price",
            "prices": prices or {},
        }

    def build_photo_keyboard(self) -> dict[str, str]:
        return {"keyboard": "photo"}

    def build_submit_keyboard(self) -> dict[str, str]:
        return {"keyboard": "submit"}

    def build_policy_answer_keyboard(self, question_index: int) -> dict[str, int]:
        return {
            "keyboard": "policy_answer",
            "question_index": question_index,
        }

    def build_policy_retry_keyboard(self) -> dict[str, str]:
        return {"keyboard": "policy_retry"}

    def build_my_service_status_keyboard(self) -> dict[str, str]:
        return {"keyboard": "my_service_status"}

    def build_existing_registration_keyboard(self) -> dict[str, str]:
        return {"keyboard": "existing_registration"}

    def build_delete_profile_confirm_keyboard(self) -> dict[str, str]:
        return {"keyboard": "delete_profile_confirm"}

    def build_provider_menu_keyboard(self, is_visible: bool = True) -> dict[str, Any]:
        return {
            "keyboard": "provider_menu",
            "is_visible": is_visible,
        }

    def build_offline_menu_keyboard(self) -> dict[str, str]:
        return {"keyboard": "offline_menu"}

    def build_contact_request_decision_keyboard(self, contact_request_id: int) -> dict[str, Any]:
        return {"keyboard": "contact_decision", "contact_request_id": contact_request_id}

    def build_profile_edit_keyboard(self) -> dict[str, str]:
        return {"keyboard": "profile_edit"}

    def build_profile_category_keyboard(self) -> dict[str, str]:
        return {"keyboard": "profile_category"}

    def build_profile_price_keyboard(self, prices: dict | None = None) -> dict[str, Any]:
        return {
            "keyboard": "profile_price",
            "prices": prices or {},
        }

    def build_profile_photo_keyboard(self) -> dict[str, str]:
        return {"keyboard": "profile_photo"}

    def remove_reply_keyboard(self) -> dict[str, str]:
        return {"keyboard": "remove"}

    def request_contact(self, chat_id: int) -> bool:
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": "request contact",
                "reply_markup": {"keyboard": "contact"},
            }
        )
        return True

    def request_location(self, chat_id: int) -> bool:
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": "request location",
                "reply_markup": {"keyboard": "location"},
            }
        )
        return True

    def send_photo(self, chat_id: int, photo_file_id: str, caption: str = "") -> bool:
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": f"photo:{photo_file_id}",
                "reply_markup": caption,
            }
        )
        return True


@pytest.fixture(autouse=True)
def reset_fake_bot_service():
    FakeTelegramBotService.instances = []


def create_policy_accepted_user(
    telegram_id: int,
    **kwargs,
) -> TelegramUser:
    defaults = {
        "policy_accepted_at": timezone.now(),
        "policy_version": POLICY_VERSION,
    }
    defaults.update(kwargs)
    return TelegramUser.objects.create(
        telegram_id=telegram_id,
        **defaults,
    )


@override_settings(TELEGRAM_MINI_APP_URL="https://example.com/marketplace")
def test_start_menu_contains_required_buttons(monkeypatch):
    service = TelegramBotService.__new__(TelegramBotService)
    sent: dict[str, Any] = {}

    def fake_send_text(
        chat_id: int,
        text: str,
        reply_markup: Any | None = None,
    ) -> bool:
        sent["chat_id"] = chat_id
        sent["text"] = text
        sent["reply_markup"] = reply_markup
        return True

    monkeypatch.setattr(service, "send_text", fake_send_text)

    assert service.send_start_menu(chat_id=123456) is True

    keyboard = sent["reply_markup"].inline_keyboard
    assert sent["chat_id"] == 123456
    assert "Telegram Service Marketplace" in sent["text"]
    assert keyboard[0][0].text == "🛒 Open Marketplace"
    assert keyboard[0][0].web_app.url == "https://example.com/marketplace"
    assert keyboard[1][0].text == "🛠 Create Service"
    assert keyboard[1][0].callback_data == "registration:create_service"
    assert keyboard[1][1].text == "📋 My Service"
    assert keyboard[1][1].callback_data == "registration:my_service"
    assert keyboard[2][0].text == "🔔 Notifications"
    assert keyboard[2][0].callback_data == "notifications:open"


@pytest.mark.django_db
@override_settings(
    BOT_WEBHOOK_SECRET="test-secret",
    TELEGRAM_BOT_TOKEN="123456:test-token",
    BOT_WEBHOOK_ASYNC=False,
)
def test_webhook_routes_start_command(api_client, monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)

    response = api_client.post(
        "/api/bot/webhook/",
        data={
            "update_id": 1001,
            "message": {
                "message_id": 10,
                "chat": {
                    "id": 777,
                    "type": "private",
                },
                "from": {
                    "id": 888,
                    "is_bot": False,
                    "first_name": "Customer",
                },
                "text": "/start",
            },
        },
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret",
    )

    payload = json.loads(response.content.decode("utf-8"))
    fake_service = FakeTelegramBotService.instances[0]

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["route"] == "policy.gate.text"
    assert fake_service.start_menu_chat_ids == []
    assert "እንኳን" in fake_service.sent_messages[0]["text"]
    assert fake_service.sent_messages[1]["reply_markup"] == {
        "keyboard": "policy_answer",
        "question_index": 0,
    }


@pytest.mark.django_db
@override_settings(
    BOT_WEBHOOK_SECRET="test-secret",
    TELEGRAM_BOT_TOKEN="123456:test-token",
    BOT_WEBHOOK_ASYNC=True,
)
def test_webhook_queues_update_without_inline_telegram_send(api_client, monkeypatch):
    submitted_updates: list[dict[str, Any]] = []

    class FakeExecutor:
        def submit(self, fn, update_data):
            submitted_updates.append(update_data)
            return None

    monkeypatch.setattr("bot.dispatcher._executor", FakeExecutor())

    response = api_client.post(
        "/api/bot/webhook/",
        data={
            "update_id": 2001,
            "message": {
                "message_id": 20,
                "chat": {
                    "id": 777,
                    "type": "private",
                },
                "from": {
                    "id": 888,
                    "is_bot": False,
                    "first_name": "Customer",
                },
                "text": "/start",
            },
        },
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret",
    )

    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["handled"] is True
    assert payload["route"] == "webhook.queued"
    assert submitted_updates[0]["update_id"] == 2001


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_notification_callback_is_routed_safely(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    create_policy_accepted_user(888)

    result = handle_telegram_update(
        {
            "update_id": 1002,
            "callback_query": {
                "id": "callback-1",
                "from": {
                    "id": 888,
                    "is_bot": False,
                    "first_name": "Customer",
                },
                "message": {
                    "message_id": 11,
                    "chat": {
                        "id": 777,
                        "type": "private",
                    },
                },
                "data": "notifications:open",
            },
        }
    )

    fake_service = FakeTelegramBotService.instances[0]

    assert result.handled is True
    assert result.route == "notifications.callback"
    assert fake_service.answered_callbacks == [
        {
            "callback_query_id": "callback-1",
            "text": "Received",
        }
    ]
    assert fake_service.sent_messages[0]["chat_id"] == 777
    assert fake_service.sent_messages[0]["text"] == "No notifications are waiting in this chat right now."


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_unknown_callback_is_acknowledged_and_reported(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    create_policy_accepted_user(888)

    result = handle_telegram_update(
        {
            "update_id": 1003,
            "callback_query": {
                "id": "callback-2",
                "from": {
                    "id": 888,
                    "is_bot": False,
                    "first_name": "Customer",
                },
                "message": {
                    "message_id": 12,
                    "chat": {
                        "id": 777,
                        "type": "private",
                    },
                },
                "data": "unknown:action",
            },
        }
    )

    fake_service = FakeTelegramBotService.instances[0]

    assert result.handled is False
    assert result.route == "invalid_state"
    assert fake_service.answered_callbacks == [
        {
            "callback_query_id": "callback-2",
            "text": "Unknown action",
        }
    ]
    assert fake_service.sent_messages[0]["text"] == (
        "That action is not available from this screen. Use /start to reopen the menu."
    )


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_create_service_requires_telegram_username(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    create_policy_accepted_user(888, role=TelegramUser.Role.PROVIDER)

    result = handle_telegram_update(
        {
            "update_id": 1004,
            "callback_query": {
                "id": "callback-3",
                "from": {
                    "id": 888,
                    "is_bot": False,
                    "first_name": "Customer",
                },
                "message": {
                    "message_id": 13,
                    "chat": {
                        "id": 777,
                        "type": "private",
                    },
                },
                "data": "registration:create_service",
            },
        }
    )

    fake_service = FakeTelegramBotService.instances[0]

    assert result.handled is False
    assert result.route == "registration.username_required"
    assert "Telegram username" in fake_service.sent_messages[0]["text"]


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_customer_create_service_starts_provider_registration(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    create_policy_accepted_user(887, role=TelegramUser.Role.CUSTOMER, customer_latitude=Decimal("9.03"), customer_longitude=Decimal("38.74"))
    ServiceCategory.objects.get_or_create(name="Doggy", defaults={"active": True})

    result = handle_telegram_update(
        {
            "update_id": 10041,
            "callback_query": {
                "id": "callback-customer-browse",
                "from": {
                    "id": 887,
                    "is_bot": False,
                    "first_name": "Customer",
                    "username": "test_customer",
                },
                "message": {
                    "message_id": 131,
                    "chat": {
                        "id": 887,
                        "type": "private",
                    },
                },
                "data": "registration:create_service",
            },
        }
    )

    fake_service = FakeTelegramBotService.instances[0]

    assert result.handled is True
    assert result.route == "registration.start"
    assert "Share your primary provider phone" in fake_service.sent_messages[0]["text"]


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_customer_category_callback_sends_filtered_miniapp_button(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    create_policy_accepted_user(886, role=TelegramUser.Role.CUSTOMER)
    category, _ = ServiceCategory.objects.get_or_create(
        name="Doggy",
        defaults={"active": True},
    )

    result = handle_telegram_update(
        {
            "update_id": 10042,
            "callback_query": {
                "id": "callback-customer-category",
                "from": {
                    "id": 886,
                    "is_bot": False,
                    "first_name": "Customer",
                },
                "message": {
                    "message_id": 132,
                    "chat": {
                        "id": 886,
                        "type": "private",
                    },
                },
                "data": "customer:browse:category:Doggy",
            },
        }
    )

    fake_service = FakeTelegramBotService.instances[0]

    assert result.handled is True
    assert result.route == "customer.browse.open_miniapp"
    assert fake_service.sent_messages[0]["reply_markup"] == {
        "text": "Open Providers",
        "screen": "swipe",
        "query_params": {"category_id": category.id},
    }


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_my_service_callback_shows_real_application_status(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider = create_policy_accepted_user(
        telegram_id=889,
        role=TelegramUser.Role.PROVIDER,
        telegram_username="provider_status",
    )
    category = ServiceCategory.objects.create(name="Status Category")
    ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="28",
        description="Reliable electrical repair service.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.PENDING,
    )

    result = handle_telegram_update(
        {
            "update_id": 1005,
            "callback_query": {
                "id": "callback-4",
                "from": {
                    "id": 889,
                    "is_bot": False,
                    "first_name": "Provider",
                    "username": "provider_status",
                },
                "message": {
                    "message_id": 14,
                    "chat": {
                        "id": 889,
                        "type": "private",
                    },
                },
                "data": "registration:my_service",
            },
        }
    )

    fake_service = FakeTelegramBotService.instances[0]

    assert result.handled is True
    assert result.route == "registration.my_service"
    assert "Pending admin review" in fake_service.sent_messages[0]["text"]
    assert fake_service.sent_messages[0]["reply_markup"] == {"keyboard": "my_service_status"}


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_create_service_is_blocked_when_provider_profile_exists(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider = create_policy_accepted_user(
        telegram_id=890,
        role=TelegramUser.Role.PROVIDER,
        telegram_username="already_registered",
    )
    category = ServiceCategory.objects.create(name="Existing Category")
    service = ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="31",
        description="Already submitted profile.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.PENDING,
    )

    result = handle_telegram_update(
        {
            "update_id": 1006,
            "callback_query": {
                "id": "callback-5",
                "from": {
                    "id": 890,
                    "is_bot": False,
                    "first_name": "Provider",
                    "username": "already_registered",
                },
                "message": {
                    "message_id": 15,
                    "chat": {
                        "id": 890,
                        "type": "private",
                    },
                },
                "data": "registration:create_service",
            },
        }
    )

    fake_service = FakeTelegramBotService.instances[0]

    assert result.handled is False
    assert result.route == "registration.existing_service_blocked"
    assert f"Service ID: {service.id}" in fake_service.sent_messages[0]["text"]
    assert "Photos:" in fake_service.sent_messages[0]["text"]
    assert fake_service.sent_messages[0]["reply_markup"] == {"keyboard": "existing_registration"}


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_registration_review_sends_submit_prompt_after_photos(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    create_policy_accepted_user(
        891,
        role=TelegramUser.Role.PROVIDER,
        telegram_username="photo_order",
    )
    BotRegistrationSession.objects.create(
        telegram_user_id=891,
        chat_id=891,
        state=BotRegistrationSession.State.PHOTOS,
        data={
            "role": TelegramUser.Role.PROVIDER,
            "telegram_username": "photo_order",
            "phone_number": "+251911111111",
            "secondary_phone_number": "",
            "category": "Doggy",
            "title": "29",
            "description": "Reliable electrical work.",
            "location": {
                "source": "gps",
                "latitude": "9.030000",
                "longitude": "38.740000",
            },
            "prices": {
                "half_day": "500",
            },
            "photos": [
                {
                    "telegram_file_id": "photo_file_1",
                    "order_index": 1,
                }
            ],
        },
    )

    result = handle_telegram_update(
        {
            "update_id": 1007,
            "callback_query": {
                "id": "callback-6",
                "from": {
                    "id": 891,
                    "is_bot": False,
                    "first_name": "Provider",
                    "username": "photo_order",
                },
                "message": {
                    "message_id": 16,
                    "chat": {
                        "id": 891,
                        "type": "private",
                    },
                },
                "data": "registration:photos_done",
            },
        }
    )

    fake_service = FakeTelegramBotService.instances[0]

    assert result.handled is True
    assert fake_service.sent_messages[0]["reply_markup"] is None
    assert fake_service.sent_messages[1]["text"] == "photo:photo_file_1"
    assert "Submit this registration draft" in fake_service.sent_messages[2]["text"]
    assert fake_service.sent_messages[2]["reply_markup"] == {"keyboard": "submit"}


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="123456:test-token")
def test_offline_provider_is_locked_until_go_online(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider = create_policy_accepted_user(
        telegram_id=892,
        role=TelegramUser.Role.PROVIDER,
        telegram_username="offline_provider",
    )
    category = ServiceCategory.objects.create(name="Offline Category")
    service = ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="35",
        description="Offline provider profile.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        visibility_status=ServiceProfile.VisibilityStatus.OFF,
    )

    locked_result = handle_telegram_update(
        {
            "update_id": 1008,
            "message": {
                "message_id": 17,
                "chat": {
                    "id": 892,
                    "type": "private",
                },
                "from": {
                    "id": 892,
                    "is_bot": False,
                    "first_name": "Provider",
                    "username": "offline_provider",
                },
                "text": "hello",
            },
        }
    )

    online_result = handle_telegram_update(
        {
            "update_id": 1009,
            "message": {
                "message_id": 18,
                "chat": {
                    "id": 892,
                    "type": "private",
                },
                "from": {
                    "id": 892,
                    "is_bot": False,
                    "first_name": "Provider",
                    "username": "offline_provider",
                },
                "text": "Go Online",
            },
        }
    )

    service.refresh_from_db()
    fake_service = FakeTelegramBotService.instances[0]

    assert locked_result.route == "profile.offline_locked"
    assert "YOU ARE OFFLINE" in fake_service.sent_messages[0]["text"]
    assert fake_service.sent_messages[0]["reply_markup"] == {"keyboard": "offline_menu"}
    assert online_result.route == "profile.go_online"
    assert service.visibility_status == ServiceProfile.VisibilityStatus.ON


def _setup_provider_with_contact(
    telegram_id: int,
    username: str,
    first_name: str | None = None,
    customer_telegram_id: int | None = None,
    created_at_age: float = 2.0,
) -> tuple[TelegramUser, TelegramUser, ServiceProfile, ContactRequest]:
    provider = TelegramUser.objects.create(
        telegram_id=telegram_id,
        telegram_username=username,
        role=TelegramUser.Role.PROVIDER,
        first_name=first_name or username,
    )
    customer = TelegramUser.objects.create(
        telegram_id=customer_telegram_id or telegram_id + 1000,
        telegram_username=f"customer_of_{username}",
        role=TelegramUser.Role.CUSTOMER,
        first_name="Test Customer",
    )
    category = ServiceCategory.objects.create(name="Alert Category")
    service = ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="Alert Test Service",
        description="Test service for pending alert.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )
    contact_request = ContactRequest.objects.create(
        customer=customer,
        provider=provider,
        service=service,
        status=ContactRequest.Status.PROVIDER_PENDING,
    )
    ContactRequest.objects.filter(pk=contact_request.pk).update(
        created_at=timezone.now() - timedelta(hours=created_at_age),
    )
    contact_request.refresh_from_db()
    return provider, customer, service, contact_request


@pytest.mark.django_db
def test_pending_alert_sent_on_start_command(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider, customer, service, contact_request = _setup_provider_with_contact(
        telegram_id=901, username="alert_provider_start",
    )

    handle_telegram_update(
        {
            "update_id": 2001,
            "message": {
                "message_id": 1,
                "chat": {"id": 901, "type": "private"},
                "from": {
                    "id": 901, "is_bot": False,
                    "first_name": "Provider", "username": "alert_provider_start",
                },
                "text": "/start",
            },
        }
    )
    fake_service = FakeTelegramBotService.instances[0]
    alert_msg = next(
        (m for m in fake_service.sent_messages if "pending service request" in m["text"]),
        None,
    )
    assert alert_msg is not None
    assert customer.get_display_name() in alert_msg["text"]
    assert service.title in alert_msg["text"]
    assert alert_msg["reply_markup"]["keyboard"] == "contact_decision"
    assert alert_msg["reply_markup"]["contact_request_id"] == contact_request.id


@pytest.mark.django_db
def test_pending_alert_sent_on_regular_message(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider, customer, service, contact_request = _setup_provider_with_contact(
        telegram_id=902, username="alert_provider_msg",
    )

    handle_telegram_update(
        {
            "update_id": 2002,
            "message": {
                "message_id": 2,
                "chat": {"id": 902, "type": "private"},
                "from": {
                    "id": 902, "is_bot": False,
                    "first_name": "Provider", "username": "alert_provider_msg",
                },
                "text": "hello",
            },
        }
    )
    fake_service = FakeTelegramBotService.instances[0]
    alert_msg = next(
        (m for m in fake_service.sent_messages if "pending service request" in m["text"]),
        None,
    )
    assert alert_msg is not None


@pytest.mark.django_db
def test_pending_alert_not_sent_when_no_pending_request(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider = TelegramUser.objects.create(
        telegram_id=903, telegram_username="no_pending",
        role=TelegramUser.Role.PROVIDER, first_name="No Pending",
    )

    handle_telegram_update(
        {
            "update_id": 2003,
            "message": {
                "message_id": 3,
                "chat": {"id": 903, "type": "private"},
                "from": {
                    "id": 903, "is_bot": False,
                    "first_name": "Provider", "username": "no_pending",
                },
                "text": "/start",
            },
        }
    )
    fake_service = FakeTelegramBotService.instances[0]
    alert_msg = next(
        (m for m in fake_service.sent_messages if "pending service request" in m["text"]),
        None,
    )
    assert alert_msg is None


@pytest.mark.django_db
def test_pending_alert_not_sent_on_contact_callback(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider, customer, service, contact_request = _setup_provider_with_contact(
        telegram_id=904, username="alert_callback",
    )

    handle_telegram_update(
        {
            "update_id": 2004,
            "callback_query": {
                "id": "cb2004",
                "chat_instance": "ci2004",
                "from": {
                    "id": 904, "is_bot": False,
                    "first_name": "Provider", "username": "alert_callback",
                },
                "message": {
                    "message_id": 10,
                    "chat": {"id": 904, "type": "private"},
                },
                "data": f"contact:{contact_request.id}:accept",
            },
        }
    )
    fake_service = FakeTelegramBotService.instances[0]
    alert_msg = next(
        (m for m in fake_service.sent_messages if "pending service request" in m["text"]),
        None,
    )
    assert alert_msg is None


@pytest.mark.django_db
def test_pending_alert_not_sent_on_edit_profile_message(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider, customer, service, contact_request = _setup_provider_with_contact(
        telegram_id=906,
        username="alert_edit_profile",
    )
    provider.policy_accepted_at = timezone.now()
    provider.policy_version = POLICY_VERSION
    provider.save(update_fields=["policy_accepted_at", "policy_version", "updated_at"])

    handle_telegram_update(
        {
            "update_id": 2006,
            "message": {
                "message_id": 6,
                "chat": {"id": 906, "type": "private"},
                "from": {
                    "id": 906,
                    "is_bot": False,
                    "first_name": "Provider",
                    "username": "alert_edit_profile",
                },
                "text": "Edit Profile",
            },
        }
    )
    fake_service = FakeTelegramBotService.instances[0]

    assert any(
        "Choose what you want to edit" in message["text"]
        for message in fake_service.sent_messages
    )
    alert_msg = next(
        (m for m in fake_service.sent_messages if "pending service request" in m["text"]),
        None,
    )
    assert alert_msg is None


@pytest.mark.django_db
def test_pending_alert_not_sent_when_request_is_newer_than_1_hour(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    provider, customer, service, contact_request = _setup_provider_with_contact(
        telegram_id=905, username="alert_fresh", created_at_age=0.3,
    )

    handle_telegram_update(
        {
            "update_id": 2005,
            "message": {
                "message_id": 5,
                "chat": {"id": 905, "type": "private"},
                "from": {
                    "id": 905, "is_bot": False,
                    "first_name": "Provider", "username": "alert_fresh",
                },
                "text": "/start",
            },
        }
    )
    fake_service = FakeTelegramBotService.instances[0]
    alert_msg = next(
        (m for m in fake_service.sent_messages if "pending service request" in m["text"]),
        None,
    )
    assert alert_msg is None


@pytest.mark.django_db
def test_validate_ethiopia_coordinates_within_box():
    valid, error = validate_ethiopia_coordinates(Decimal("9.03"), Decimal("38.74"))
    assert valid is True
    assert error is None


@pytest.mark.django_db
def test_validate_ethiopia_coordinates_outside_low_lat():
    valid, error = validate_ethiopia_coordinates(Decimal("2.0"), Decimal("38.74"))
    assert valid is False
    assert error is not None


@pytest.mark.django_db
def test_validate_ethiopia_coordinates_outside_high_lon():
    valid, error = validate_ethiopia_coordinates(Decimal("9.03"), Decimal("50.0"))
    assert valid is False
    assert error is not None


@pytest.mark.django_db
def test_is_far_from_addis_nearby():
    assert is_far_from_addis(9.03, 38.74) is False


@pytest.mark.django_db
def test_is_far_from_addis_far_away():
    assert is_far_from_addis(14.0, 45.0) is True


@pytest.mark.django_db
def test_customer_location_stored_via_handle_location_message(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    user = create_policy_accepted_user(
        telegram_id=910, role=TelegramUser.Role.CUSTOMER,
        telegram_username="gps_customer",
    )

    handle_telegram_update(
        {
            "update_id": 3001,
            "message": {
                "message_id": 1,
                "chat": {"id": 910, "type": "private"},
                "from": {"id": 910, "is_bot": False, "first_name": "GPS", "username": "gps_customer"},
                "location": {"latitude": 9.03, "longitude": 38.74},
            },
        }
    )
    user.refresh_from_db()
    assert user.has_customer_location is True
    assert float(user.customer_latitude) == 9.03
    assert float(user.customer_longitude) == 38.74


@pytest.mark.django_db
def test_customer_outside_ethiopia_rejected(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    user = create_policy_accepted_user(
        telegram_id=911, role=TelegramUser.Role.CUSTOMER,
        telegram_username="outside_customer",
    )

    handle_telegram_update(
        {
            "update_id": 3002,
            "message": {
                "message_id": 2,
                "chat": {"id": 911, "type": "private"},
                "from": {"id": 911, "is_bot": False, "first_name": "Outside", "username": "outside_customer"},
                "location": {"latitude": 2.0, "longitude": 38.74},
            },
        }
    )
    user.refresh_from_db()
    assert user.has_customer_location is False
    fake = FakeTelegramBotService.instances[0]
    outside_msg = next(
        (m for m in fake.sent_messages if "outside Ethiopia" in m["text"]),
        None,
    )
    assert outside_msg is not None


@pytest.mark.django_db
def test_discovery_intercepts_when_customer_lacks_location(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    user = create_policy_accepted_user(
        telegram_id=912, role=TelegramUser.Role.CUSTOMER,
        telegram_username="no_location_customer",
    )

    handle_telegram_update(
        {
            "update_id": 3003,
            "message": {
                "message_id": 3,
                "chat": {"id": 912, "type": "private"},
                "from": {"id": 912, "is_bot": False, "first_name": "NoLoc", "username": "no_location_customer"},
                "text": "/discover",
            },
        }
    )
    fake = FakeTelegramBotService.instances[0]
    location_req = next(
        (m for m in fake.sent_messages if isinstance(m.get("reply_markup"), dict) and m["reply_markup"].get("keyboard") == "location"),
        None,
    )
    assert location_req is not None, "Should request location instead of showing mini app"


@pytest.mark.django_db
def test_discovery_proceeds_when_customer_has_location(monkeypatch):
    monkeypatch.setattr("bot.handlers.TelegramBotService", FakeTelegramBotService)
    user = create_policy_accepted_user(
        telegram_id=913, role=TelegramUser.Role.CUSTOMER,
        telegram_username="has_location_customer",
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
    )

    handle_telegram_update(
        {
            "update_id": 3004,
            "message": {
                "message_id": 4,
                "chat": {"id": 913, "type": "private"},
                "from": {"id": 913, "is_bot": False, "first_name": "HasLoc", "username": "has_location_customer"},
                "text": "/discover",
            },
        }
    )
    fake = FakeTelegramBotService.instances[0]
    mini_app_msg = next(
        (m for m in fake.sent_messages if "Open Discovery" in str(m.get("reply_markup", {}))),
        None,
    )
    assert mini_app_msg is not None, "Should show mini app link"
