from urllib import response

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from approvals.models import AdminSettings, ContactRequest
from services.models import ServiceCategory, ServiceProfile
from swipes.models import SwipeHistory


@pytest.fixture
def customer():
    return TelegramUser.objects.create(
        telegram_id=88001,
        role=TelegramUser.Role.CUSTOMER,
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
    )


@pytest.fixture
def banned_customer():
    return TelegramUser.objects.create(
        telegram_id=88002,
        role=TelegramUser.Role.CUSTOMER,
        is_banned=True,
    )

@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=88003,
        role=TelegramUser.Role.PROVIDER,
        first_name="Provider",
        last_name="Person",
        telegram_username="provider_person",
        phone_number="+251911111111",
    )


@pytest.fixture
def auth_user(customer):
    return User.objects.create_user(
        username=f"telegram_{customer.telegram_id}",
    )


@pytest.fixture
def banned_auth_user(banned_customer):
    return User.objects.create_user(
        username=f"telegram_{banned_customer.telegram_id}",
    )


@pytest.fixture
def token(auth_user):
    token, _ = Token.objects.get_or_create(user=auth_user)
    return token


@pytest.fixture
def banned_token(banned_auth_user):
    token, _ = Token.objects.get_or_create(user=banned_auth_user)
    return token


@pytest.fixture
def authenticated_client(api_client, token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )
    return api_client


@pytest.fixture
def banned_client(api_client, banned_token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {banned_token.key}"
    )
    return api_client


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Swipe Contact Category"
    )


@pytest.fixture
def approved_service(provider, category):
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="Swipe Contact Service",
        description="Swipe Contact Description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )


@pytest.fixture(autouse=True)
def disable_contact_request_notifications(monkeypatch):
    monkeypatch.setattr(
        "approvals.contact_workflow.queue_provider_confirmation_message",
        lambda contact_request_id: None,
    )


@pytest.mark.django_db
def test_swipe_like_creates_swipe_and_provider_pending_contact_request(
    authenticated_client,
    approved_service,
):
    response = authenticated_client.post(
        "/api/swipe/like/",
        {
            "service_id": approved_service.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["success"] is True
    assert response.data["swipe"]["swipe_status"] == SwipeHistory.SwipeStatus.LIKED
    assert response.data["contact_request"]["status"] == ContactRequest.Status.PROVIDER_PENDING
    assert response.data["contact_request"]["contact_visible"] is False
    assert response.data["contact_request"]["provider_confirmation_required"] is True
    assert "provider_contact" not in response.data["contact_request"]
    assert SwipeHistory.objects.count() == 1
    assert ContactRequest.objects.count() == 1
    approved_service.refresh_from_db()
    assert approved_service.likes_count == 1


@pytest.mark.django_db
def test_swipe_like_reuses_existing_contact_request(
    authenticated_client,
    customer,
    provider,
    approved_service,
):
    existing_request = ContactRequest.objects.create(
        customer=customer,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    response = authenticated_client.post(
        "/api/swipe/like/",
        {
            "service_id": approved_service.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert ContactRequest.objects.count() == 1
    assert response.data["contact_request"]["id"] == existing_request.id


@pytest.mark.django_db
def test_swipe_like_still_requires_provider_confirmation_when_auto_approval_enabled(
    authenticated_client,
    approved_service,
):
    settings = AdminSettings.get_settings()
    settings.auto_approve_requests = True
    settings.save()

    response = authenticated_client.post(
        "/api/swipe/like/",
        {
            "service_id": approved_service.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["contact_request"]["status"] == ContactRequest.Status.PROVIDER_PENDING
    assert response.data["contact_request"]["contact_visible"] is False
    assert response.data["contact_request"]["provider_confirmation_required"] is True
    assert "provider_contact" not in response.data["contact_request"]


@pytest.mark.django_db
def test_swipe_dislike_creates_dislike_without_contact_request(
    authenticated_client,
    approved_service,
):
    response = authenticated_client.post(
        "/api/swipe/dislike/",
        {
            "service_id": approved_service.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["success"] is True
    assert response.data["swipe"]["swipe_status"] == SwipeHistory.SwipeStatus.DISLIKED
    assert response.data["swipe"]["reset_at"] is not None
    assert SwipeHistory.objects.count() == 1
    assert ContactRequest.objects.count() == 0


@pytest.mark.django_db
def test_contact_request_endpoint_creates_provider_pending_request(
    authenticated_client,
    approved_service,
):
    response = authenticated_client.post(
        "/api/contact-request/",
        {
            "service_id": approved_service.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["success"] is True
    assert response.data["contact_request"]["status"] == ContactRequest.Status.PROVIDER_PENDING
    assert response.data["contact_request"]["contact_visible"] is False
    assert response.data["contact_request"]["provider_confirmation_required"] is True


@pytest.mark.django_db
def test_contact_request_status_hides_contact_when_pending(
    authenticated_client,
    customer,
    provider,
    approved_service,
):
    ContactRequest.objects.create(
        customer=customer,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    response = authenticated_client.get(
        "/api/contact-request/status/",
        {
            "service_id": approved_service.id,
        },
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["contact_request"]["status"] == ContactRequest.Status.PENDING
    assert response.data["contact_request"]["contact_visible"] is False
    assert "provider_contact" not in response.data["contact_request"]


@pytest.mark.django_db
def test_contact_request_status_reveals_contact_when_approved(
    authenticated_client,
    customer,
    provider,
    approved_service,
):
    ContactRequest.objects.create(
        customer=customer,
        provider=provider,
        status=ContactRequest.Status.APPROVED,
    )

    response = authenticated_client.get(
        "/api/contact-request/status/",
        {
            "service_id": approved_service.id,
        },
    )

    assert response.status_code == 200
    assert response.data["contact_request"]["contact_visible"] is True
    assert response.data["contact_request"]["provider_contact"]["contact_type"] == "telegram_username"
    assert response.data["contact_request"]["provider_contact"]["contact_value"] == "provider_person"


@pytest.mark.django_db
def test_banned_customer_cannot_like(banned_client, approved_service):
    response = banned_client.post(
        "/api/swipe/like/",
        {
            "service_id": approved_service.id,
        },
        format="json",
    )

    assert response.status_code == 403
    assert response.data["success"] is False


@pytest.mark.django_db
def test_invalid_service_id_is_rejected(authenticated_client):
    response = authenticated_client.post(
        "/api/swipe/like/",
        {
            "service_id": 999999,
        },
        format="json",
    )

    assert response.status_code == 404
    assert response.data["success"] is False
