import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from decimal import Decimal

from accounts.models import TelegramUser
from approvals.models import ContactRequest
from services.models import ServiceCategory, ServiceProfile
from swipes.models import SwipeHistory


def make_authenticated_client(api_client, customer):
    auth_user = User.objects.create_user(
        username=f"telegram_{customer.telegram_id}",
    )
    token, _ = Token.objects.get_or_create(user=auth_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


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


def create_existing_contact_requests(customer, count, start_telegram_id=920000):
    for index in range(count):
        provider = make_provider(
            telegram_id=start_telegram_id + index,
            name=f"Existing Provider {index}",
        )
        ContactRequest.objects.create(
            customer=customer,
            provider=provider,
        )


@pytest.mark.django_db
def test_fourth_immediate_contact_request_is_progressively_paced(api_client):
    customer = make_customer()
    client = make_authenticated_client(api_client, customer)
    category = ServiceCategory.objects.create(name="Usage Policy Category")
    target_provider = make_provider(930001, "Target Provider")
    target_service = make_approved_service(
        provider=target_provider,
        category=category,
        title="Target Service",
    )

    create_existing_contact_requests(customer, count=3)

    response = client.post(
        "/api/contact-request/",
        {
            "service_id": target_service.id,
        },
        format="json",
    )

    assert response.status_code == 429
    assert response.data["success"] is False
    assert response.data["provider_protection"]["requests_today"] == 3
    assert response.data["provider_protection"]["protection_level"] == "paced"
    assert response.data["provider_protection"]["retry_after_seconds"] > 0
    assert response["Retry-After"]
    assert ContactRequest.objects.filter(customer=customer).count() == 3


@pytest.mark.django_db
def test_existing_contact_request_can_be_reused_even_after_heavy_usage(api_client):
    customer = make_customer()
    client = make_authenticated_client(api_client, customer)
    category = ServiceCategory.objects.create(name="Reuse Policy Category")
    target_provider = make_provider(940001, "Reusable Provider")
    target_service = make_approved_service(
        provider=target_provider,
        category=category,
        title="Reusable Service",
    )
    existing_request = ContactRequest.objects.create(
        customer=customer,
        provider=target_provider,
    )
    create_existing_contact_requests(
        customer,
        count=10,
        start_telegram_id=941000,
    )
    contact_count_before = ContactRequest.objects.filter(customer=customer).count()

    response = client.post(
        "/api/contact-request/",
        {
            "service_id": target_service.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["success"] is True
    assert response.data["contact_request"]["id"] == existing_request.id
    assert ContactRequest.objects.filter(customer=customer).count() == contact_count_before


@pytest.mark.django_db
def test_swipe_like_cannot_bypass_contact_usage_policy(api_client):
    customer = make_customer()
    client = make_authenticated_client(api_client, customer)
    category = ServiceCategory.objects.create(name="Swipe Usage Policy Category")
    target_provider = make_provider(950001, "Swipe Target Provider")
    target_service = make_approved_service(
        provider=target_provider,
        category=category,
        title="Swipe Target Service",
    )

    create_existing_contact_requests(customer, count=3)

    response = client.post(
        "/api/swipe/like/",
        {
            "service_id": target_service.id,
        },
        format="json",
    )

    assert response.status_code == 429
    assert response.data["success"] is False
    assert SwipeHistory.objects.filter(customer=customer).count() == 0
    assert ContactRequest.objects.filter(customer=customer).count() == 3
    assert ContactRequest.objects.filter(
        customer=customer,
        provider=target_provider,
    ).exists() is False


@pytest.mark.django_db
def test_swipe_dislike_is_not_counted_by_contact_usage_policy(api_client):
    customer = make_customer()
    client = make_authenticated_client(api_client, customer)
    category = ServiceCategory.objects.create(name="Dislike Usage Policy Category")
    target_provider = make_provider(960001, "Dislike Target Provider")
    target_service = make_approved_service(
        provider=target_provider,
        category=category,
        title="Dislike Target Service",
    )

    create_existing_contact_requests(customer, count=10)

    response = client.post(
        "/api/swipe/dislike/",
        {
            "service_id": target_service.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["success"] is True
    assert response.data["swipe"]["swipe_status"] == SwipeHistory.SwipeStatus.DISLIKED
    assert ContactRequest.objects.filter(customer=customer).count() == 10


@pytest.mark.django_db
def test_weekly_limit_blocking(api_client):
    customer = make_customer(970001)
    client = make_authenticated_client(api_client, customer)
    category = ServiceCategory.objects.create(name="Weekly Limit Category")
    target_provider = make_provider(970002, "Weekly Target Provider")
    target_service = make_approved_service(
        provider=target_provider,
        category=category,
        title="Weekly Target Service",
    )

    create_existing_contact_requests(customer, count=7, start_telegram_id=971000)

    response = client.post(
        "/api/contact-request/",
        {
            "service_id": target_service.id,
        },
        format="json",
    )

    assert response.status_code == 429
    assert response.data["success"] is False
    assert response.data["provider_protection"]["protection_level"] == "weekly_lock"
    assert "weekly" in response.data["provider_protection"]["message"].lower()


@pytest.mark.django_db
def test_weekly_check_priority(api_client):
    customer = make_customer(980001)
    client = make_authenticated_client(api_client, customer)
    category = ServiceCategory.objects.create(name="Priority Limit Category")
    target_provider = make_provider(980002, "Priority Target Provider")
    target_service = make_approved_service(
        provider=target_provider,
        category=category,
        title="Priority Target Service",
    )

    create_existing_contact_requests(customer, count=7, start_telegram_id=981000)

    response = client.post(
        "/api/contact-request/",
        {
            "service_id": target_service.id,
        },
        format="json",
    )

    assert response.status_code == 429
    assert response.data["provider_protection"]["protection_level"] == "weekly_lock"


@pytest.mark.django_db
def test_pacing_cooldowns_lookup():
    from approvals.usage_limits import evaluate_contact_request_creation
    customer = make_customer(990001)
    
    # 0 requests today -> no cooldown
    decision = evaluate_contact_request_creation(customer)
    assert decision.cooldown_seconds == 0

    # 1 request today -> no cooldown
    create_existing_contact_requests(customer, count=1, start_telegram_id=991000)
    decision = evaluate_contact_request_creation(customer)
    assert decision.cooldown_seconds == 0

    # 2 requests today -> 20 minutes (1200 seconds) cooldown
    create_existing_contact_requests(customer, count=1, start_telegram_id=992000)
    decision = evaluate_contact_request_creation(customer)
    assert decision.cooldown_seconds == 1200

    # 3 requests today -> 30 minutes (1800 seconds) cooldown
    create_existing_contact_requests(customer, count=1, start_telegram_id=993000)
    decision = evaluate_contact_request_creation(customer)
    assert decision.cooldown_seconds == 1800
