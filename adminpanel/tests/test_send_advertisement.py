from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServicePhoto, ServiceProfile


@pytest.fixture
def admin_user():
    u = User.objects.create_superuser(
        username="admin",
        password="adminpass",
        email="admin@example.com",
    )
    token, _ = Token.objects.get_or_create(user=u)
    return u, token


@pytest.fixture
def category():
    return ServiceCategory.objects.create(name="Popular Cat")


@pytest.fixture
def customer():
    return TelegramUser.objects.create(
        telegram_id=70001,
        role=TelegramUser.Role.CUSTOMER,
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
        policy_accepted_at=timezone.now(),
    )


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=70002,
        role=TelegramUser.Role.PROVIDER,
        first_name="Provider",
        phone_number="+251911111111",
    )


def make_service(provider, category, title, likes_count=0):
    service = ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title=title,
        description=f"{title} description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
        likes_count=likes_count,
    )
    ServicePhoto.objects.create(
        service=service,
        telegram_file_id=f"file_{title}",
        order_index=1,
    )
    return service


@pytest.mark.django_db
class TestSendAdvertisement:
    def _patch_executor(self):
        class SyncExecutor:
            def submit(self, fn, *args, **kwargs):
                fut = __import__("concurrent.futures").futures.Future()
                try:
                    fut.set_result(fn(*args, **kwargs))
                except Exception as e:
                    fut.set_exception(e)
                return fut
            def shutdown(self, wait=True):
                pass
        return patch("adminpanel.views._advertisement_executor", SyncExecutor())

    def test_sends_to_customers_with_policy(self, api_client, admin_user, customer, provider, category):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        make_service(provider, category, "Top Service", likes_count=10)

        with patch("adminpanel.views.TelegramBotService") as MockBot, self._patch_executor():
            mock_instance = MockBot.return_value
            mock_instance.send_photo.return_value = True

            response = api_client.post("/api/admin/send-advertisement/", format="json")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["customers_targeted"] == 1
        assert response.data["photos_sent"] >= 1

    def test_skips_customers_without_policy(self, api_client, admin_user, provider, category):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        make_service(provider, category, "Top Service", likes_count=10)

        TelegramUser.objects.create(
            telegram_id=70003,
            role=TelegramUser.Role.CUSTOMER,
            policy_accepted_at=None,
        )

        with patch("adminpanel.views.TelegramBotService") as MockBot, self._patch_executor():
            mock_instance = MockBot.return_value
            mock_instance.send_photo.return_value = True

            response = api_client.post("/api/admin/send-advertisement/", format="json")

        assert response.status_code == 200
        assert response.data["customers_targeted"] == 0

    def test_respects_max_500(self, api_client, admin_user, provider, category):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        make_service(provider, category, "Top Service", likes_count=10)

        for i in range(505):
            TelegramUser.objects.create(
                telegram_id=70100 + i,
                role=TelegramUser.Role.CUSTOMER,
                policy_accepted_at=timezone.now(),
            )

        with patch("adminpanel.views.TelegramBotService") as MockBot, self._patch_executor():
            mock_instance = MockBot.return_value
            mock_instance.send_photo.return_value = True

            response = api_client.post("/api/admin/send-advertisement/", format="json")

        assert response.status_code == 200
        assert response.data["customers_targeted"] == 500

    def test_requires_auth(self, api_client):
        response = api_client.post("/api/admin/send-advertisement/", format="json")
        assert response.status_code == 403

    def test_non_admin_forbidden(self, api_client):
        user = User.objects.create_user(username="regular_user")
        token, _ = Token.objects.get_or_create(user=user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.post("/api/admin/send-advertisement/", format="json")
        assert response.status_code == 403

    def test_no_eligible_services(self, api_client, admin_user, customer):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        with patch("adminpanel.views.TelegramBotService") as MockBot:
            mock_instance = MockBot.return_value
            mock_instance.send_photo.return_value = True

            response = api_client.post("/api/admin/send-advertisement/", format="json")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["photos_sent"] == 0
