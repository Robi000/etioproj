from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServiceProfile
from swipes.models import SavedServiceRequest


def make_customer(telegram_id=910001):
    return TelegramUser.objects.create(
        telegram_id=telegram_id,
        role=TelegramUser.Role.CUSTOMER,
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
    )


def make_provider(telegram_id, name="Provider"):
    return TelegramUser.objects.create(
        telegram_id=telegram_id,
        role=TelegramUser.Role.PROVIDER,
        first_name=name,
        phone_number=f"+2519{telegram_id}",
    )


def make_approved_service(provider, category, title):
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title=title,
        description=f"{title} description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )


@pytest.mark.django_db
class TestSaveService:
    def setup_customer(self, telegram_id=910001):
        customer = make_customer(telegram_id)
        auth_user = User.objects.create_user(
            username=f"telegram_{customer.telegram_id}",
        )
        token, _ = Token.objects.get_or_create(user=auth_user)
        return customer, token

    def test_save_service_success(self, api_client):
        customer, token = self.setup_customer()
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        category = ServiceCategory.objects.create(name="Test Cat")
        provider = make_provider(920001)
        service = make_approved_service(provider, category, "Test Service")

        response = api_client.post(
            "/api/swipe/save/",
            {"service_id": service.id},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["success"] is True
        assert response.data["saved"] is True
        assert SavedServiceRequest.objects.filter(
            customer=customer, service=service
        ).exists()

    def test_save_service_idempotent(self, api_client):
        customer, token = self.setup_customer()
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        category = ServiceCategory.objects.create(name="Test Cat")
        provider = make_provider(920002)
        service = make_approved_service(provider, category, "Test Service")

        SavedServiceRequest.objects.create(customer=customer, service=service)

        response = api_client.post(
            "/api/swipe/save/",
            {"service_id": service.id},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["saved"] is True
        assert SavedServiceRequest.objects.filter(
            customer=customer, service=service
        ).count() == 1

    def test_save_max_three(self, api_client):
        customer, token = self.setup_customer()
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        category = ServiceCategory.objects.create(name="Test Cat")

        services = []
        for i in range(3):
            p = make_provider(920003 + i, f"Provider{i}")
            s = make_approved_service(p, category, f"Service {i}")
            services.append(s)
            SavedServiceRequest.objects.create(customer=customer, service=s)

        extra_provider = make_provider(920006, "ExtraProvider")
        extra = make_approved_service(extra_provider, category, "Extra Service")
        response = api_client.post(
            "/api/swipe/save/",
            {"service_id": extra.id},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False
        assert "up to 3" in response.data["error"].lower()

    def test_save_unauthenticated(self, api_client):
        response = api_client.post(
            "/api/swipe/save/",
            {"service_id": 1},
            format="json",
        )

        assert response.status_code == 403

    def test_save_invalid_service_id(self, api_client):
        customer, token = self.setup_customer()
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.post(
            "/api/swipe/save/",
            {"service_id": 99999},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False


@pytest.mark.django_db
class TestUnsaveService:
    def test_unsave_existing(self, api_client):
        customer = make_customer(930001)
        auth_user = User.objects.create_user(
            username=f"telegram_{customer.telegram_id}",
        )
        token, _ = Token.objects.get_or_create(user=auth_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        category = ServiceCategory.objects.create(name="Test Cat")
        provider = make_provider(930002)
        service = make_approved_service(provider, category, "Test Service")
        SavedServiceRequest.objects.create(customer=customer, service=service)

        response = api_client.delete(
            f"/api/swipe/save/{service.id}/",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["deleted"] is True
        assert not SavedServiceRequest.objects.filter(
            customer=customer, service=service
        ).exists()

    def test_unsave_nonexistent(self, api_client):
        customer = make_customer(930003)
        auth_user = User.objects.create_user(
            username=f"telegram_{customer.telegram_id}",
        )
        token, _ = Token.objects.get_or_create(user=auth_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.delete("/api/swipe/save/99999/")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["deleted"] is False

    def test_unsave_unauthenticated(self, api_client):
        response = api_client.delete("/api/swipe/save/1/")
        assert response.status_code == 403


@pytest.mark.django_db
class TestSavedServices:
    def test_list_saved(self, api_client):
        customer = make_customer(940001)
        auth_user = User.objects.create_user(
            username=f"telegram_{customer.telegram_id}",
        )
        token, _ = Token.objects.get_or_create(user=auth_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        category = ServiceCategory.objects.create(name="Test Cat")
        provider = make_provider(940002)
        service = make_approved_service(provider, category, "Saved Service")
        SavedServiceRequest.objects.create(customer=customer, service=service)

        response = api_client.get("/api/swipe/saved/")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert len(response.data["services"]) == 1
        assert response.data["services"][0]["id"] == service.id
        assert response.data["services"][0]["title"] == "Saved Service"
        assert "saved_at" in response.data["services"][0]

    def test_list_saved_empty(self, api_client):
        customer = make_customer(940003)
        auth_user = User.objects.create_user(
            username=f"telegram_{customer.telegram_id}",
        )
        token, _ = Token.objects.get_or_create(user=auth_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.get("/api/swipe/saved/")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["services"] == []

    def test_saved_unauthenticated(self, api_client):
        response = api_client.get("/api/swipe/saved/")
        assert response.status_code == 403
