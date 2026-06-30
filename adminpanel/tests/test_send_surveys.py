from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from approvals.models import ContactRequest, CustomerSurvey
from services.models import ServiceCategory, ServiceProfile


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
def customer():
    return TelegramUser.objects.create(
        telegram_id=80001,
        role=TelegramUser.Role.CUSTOMER,
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
    )


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=80002,
        role=TelegramUser.Role.PROVIDER,
        first_name="Provider",
        phone_number="+251911111111",
        telegram_username="provider_abc",
    )


@pytest.mark.django_db
class TestSendSurveys:
    def test_send_surveys_skips_recent_requests(self, api_client, admin_user, customer, provider):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        cr = ContactRequest.objects.create(
            customer=customer,
            provider=provider,
            status=ContactRequest.Status.APPROVED,
            approved_at=timezone.now() - timezone.timedelta(hours=6),
        )

        with patch("adminpanel.views.TelegramBotService") as MockBot:
            mock_instance = MockBot.return_value
            mock_instance.send_text.return_value = True

            response = api_client.post("/api/admin/send-surveys/", format="json")

        assert response.status_code == 200
        assert response.data["sent_count"] == 0

    def test_send_surveys_skips_existing_survey(self, api_client, admin_user, customer, provider):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        cr = ContactRequest.objects.create(
            customer=customer,
            provider=provider,
            status=ContactRequest.Status.APPROVED,
            approved_at=timezone.now() - timezone.timedelta(days=3),
        )
        CustomerSurvey.objects.create(
            contact_request=cr,
            sent_at=timezone.now(),
        )

        with patch("adminpanel.views.TelegramBotService") as MockBot:
            mock_instance = MockBot.return_value
            mock_instance.send_text.return_value = True

            response = api_client.post("/api/admin/send-surveys/", format="json")

        assert response.status_code == 200
        assert response.data["sent_count"] == 0

    def test_send_surveys_sends_to_eligible(self, api_client, admin_user, customer, provider):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        category = ServiceCategory.objects.create(name="Test Cat")
        service = ServiceProfile.objects.create(
            provider=provider,
            category=category,
            title="Test Service",
            description="Test description",
            city_text="Addis Ababa",
            location_source=ServiceProfile.LocationSource.CITY_TEXT,
            approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
        )

        cr = ContactRequest.objects.create(
            customer=customer,
            provider=provider,
            service=service,
            status=ContactRequest.Status.APPROVED,
            approved_at=timezone.now() - timezone.timedelta(days=3),
        )

        with patch("adminpanel.views.TelegramBotService") as MockBot:
            mock_instance = MockBot.return_value
            mock_instance.send_text.return_value = True

            response = api_client.post("/api/admin/send-surveys/", format="json")

        assert response.status_code == 200
        assert response.data["sent_count"] == 1

        survey = CustomerSurvey.objects.get(contact_request=cr)
        assert survey.sent_at is not None
        assert survey.response == ""
        assert survey.no_reason == ""

    def test_send_surveys_requires_auth(self, api_client):
        response = api_client.post("/api/admin/send-surveys/", format="json")
        assert response.status_code == 403

    def test_send_surveys_non_admin_forbidden(self, api_client):
        user = User.objects.create_user(username="regular_user")
        token, _ = Token.objects.get_or_create(user=user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.post("/api/admin/send-surveys/", format="json")
        assert response.status_code == 403
