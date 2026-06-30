from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from approvals.models import ContactRequest
from services.models import (
    ServiceCategory,
    ServicePhoto,
    ServicePrice,
    ServiceProfile,
)


def make_authenticated_client(api_client, telegram_user):
    auth_user, _ = User.objects.get_or_create(
        username=f"telegram_{telegram_user.telegram_id}",
        defaults={
            "first_name": telegram_user.first_name,
            "last_name": telegram_user.last_name,
            "is_active": not telegram_user.is_banned,
        },
    )

    token, _ = Token.objects.get_or_create(user=auth_user)

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )

    return api_client

@pytest.mark.django_db
def test_phase2_end_to_end_flow(api_client, monkeypatch):
    monkeypatch.setattr(
        "approvals.contact_workflow.queue_provider_confirmation_message",
        lambda contact_request_id: None,
    )
    monkeypatch.setattr(
        "adminpanel.views.queue_customer_admin_decision_message",
        lambda contact_request_id: None,
    )
    admin_user = TelegramUser.objects.create(
        telegram_id=100001,
        role=TelegramUser.Role.ADMIN,
    )
    provider = TelegramUser.objects.create(
    telegram_id=100002,
    role=TelegramUser.Role.PROVIDER,
    first_name="Provider",
    telegram_username="provider_integration",
    phone_number="+251933333333",
    )

    customer = TelegramUser.objects.create(
        telegram_id=100003,
        role=TelegramUser.Role.CUSTOMER,
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
    )

    category = ServiceCategory.objects.create(
        name="Phase 2 Integration Category"
    )

    provider_client = make_authenticated_client(api_client, provider)

    profile_response = provider_client.patch(
        "/api/profile/",
        {
            "first_name": "Provider Updated",
        },
        format="json",
    )
    assert profile_response.status_code == 200

    service_response = provider_client.post(
        "/api/service/",
        {
            "category_id": category.id,
            "title": "Integration Service",
            "description": "Integration service description",
            "city_text": "Addis Ababa",
            "visibility_status": ServiceProfile.VisibilityStatus.ON,
        },
        format="json",
    )
    assert service_response.status_code == 201

    service = ServiceProfile.objects.get(provider=provider)

    price_response = provider_client.patch(
        "/api/service/prices/",
        {
            "prices": [
                {
                    "price_type": ServicePrice.PriceType.HALF_DAY,
                    "amount": "500.00",
                }
            ]
        },
        format="json",
    )
    assert price_response.status_code == 200
    assert service.prices.count() == 1

    photo_response = provider_client.post(
        "/api/service/photos/",
        {
            "telegram_file_id": "integration_photo_file",
        },
        format="json",
    )
    assert photo_response.status_code == 201
    assert ServicePhoto.objects.filter(service=service).count() == 1

    admin_client = make_authenticated_client(api_client, admin_user)

    approve_service_response = admin_client.post(
        "/api/admin/service/approve/",
        {
            "service_id": service.id,
        },
        format="json",
    )
    assert approve_service_response.status_code == 200

    service.refresh_from_db()
    assert service.approval_status == ServiceProfile.ApprovalStatus.APPROVED

    customer_client = make_authenticated_client(api_client, customer)

    discovery_response = customer_client.get(
        "/api/discovery/grid/",
        {
            "category_id": category.id,
            "city_text": "Addis Ababa",
        },
    )

    assert discovery_response.status_code == 200
    assert discovery_response.data["count"] == 1
    assert discovery_response.data["results"][0]["id"] == service.id

    like_response = customer_client.post(
        "/api/swipe/like/",
        {
            "service_id": service.id,
        },
        format="json",
    )

    assert like_response.status_code == 201
    assert ContactRequest.objects.count() == 1

    contact_request = ContactRequest.objects.first()
    assert contact_request.status == ContactRequest.Status.PROVIDER_PENDING

    contact_request.status = ContactRequest.Status.PENDING
    contact_request.save(update_fields=["status"])

    admin_client = make_authenticated_client(api_client, admin_user)
    approve_contact_response = admin_client.post(
        "/api/admin/contact/approve/",
        {
            "contact_request_id": contact_request.id,
        },
        format="json",
    )

    assert approve_contact_response.status_code == 200

    customer_client = make_authenticated_client(api_client, customer)
    
    status_response = customer_client.get(
        "/api/contact-request/status/",
        {
            "service_id": service.id,
        },
    )

    assert status_response.status_code == 200
    assert status_response.data["contact_request"]["status"] == ContactRequest.Status.APPROVED
    assert status_response.data["contact_request"]["contact_visible"] is True
    assert status_response.data["contact_request"]["provider_contact"]["contact_type"] == "telegram_username"
    assert status_response.data["contact_request"]["provider_contact"]["contact_value"] == "provider_integration"
