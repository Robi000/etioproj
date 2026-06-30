import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServicePrice, ServiceProfile


@pytest.fixture
def provider_user():
    return TelegramUser.objects.create(
        telegram_id=55555,
        telegram_username="price_api_provider",
        first_name="Provider",
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def auth_user(provider_user):
    return User.objects.create_user(
        username=f"telegram_{provider_user.telegram_id}",
        first_name=provider_user.first_name,
    )


@pytest.fixture
def token(auth_user):
    token, _ = Token.objects.get_or_create(user=auth_user)
    return token


@pytest.fixture
def authenticated_client(api_client, token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )
    return api_client


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Price API Category"
    )


@pytest.fixture
def service(provider_user, category):
    return ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Price API Service",
        description="Price API Service Description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )


@pytest.mark.django_db
def test_update_prices_accepts_one_price(authenticated_client, service):
    response = authenticated_client.patch(
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

    assert response.status_code == 200
    assert response.data["success"] is True
    assert len(response.data["prices"]) == 1
    assert response.data["prices"][0]["price_type"] == ServicePrice.PriceType.HALF_DAY
    assert service.prices.count() == 1


@pytest.mark.django_db
def test_update_prices_accepts_multiple_prices(authenticated_client, service):
    response = authenticated_client.patch(
        "/api/service/prices/",
        {
            "prices": [
                {
                    "price_type": ServicePrice.PriceType.HALF_DAY,
                    "amount": "500.00",
                },
                {
                    "price_type": ServicePrice.PriceType.FULL_DAY,
                    "amount": "900.00",
                },
                {
                    "price_type": ServicePrice.PriceType.NIGHT,
                    "amount": "1200.00",
                },
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert len(response.data["prices"]) == 3
    assert service.prices.count() == 3


@pytest.mark.django_db
def test_update_prices_rejects_empty_prices(authenticated_client, service):
    response = authenticated_client.patch(
        "/api/service/prices/",
        {
            "prices": []
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False
    assert service.prices.count() == 0


@pytest.mark.django_db
def test_update_prices_rejects_invalid_price_type(authenticated_client, service):
    response = authenticated_client.patch(
        "/api/service/prices/",
        {
            "prices": [
                {
                    "price_type": "weekly",
                    "amount": "500.00",
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False
    assert service.prices.count() == 0


@pytest.mark.django_db
def test_update_prices_rejects_negative_amount(authenticated_client, service):
    response = authenticated_client.patch(
        "/api/service/prices/",
        {
            "prices": [
                {
                    "price_type": ServicePrice.PriceType.HALF_DAY,
                    "amount": "-100.00",
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False
    assert service.prices.count() == 0


@pytest.mark.django_db
def test_update_prices_rejects_duplicate_price_type(authenticated_client, service):
    response = authenticated_client.patch(
        "/api/service/prices/",
        {
            "prices": [
                {
                    "price_type": ServicePrice.PriceType.HALF_DAY,
                    "amount": "500.00",
                },
                {
                    "price_type": ServicePrice.PriceType.HALF_DAY,
                    "amount": "600.00",
                },
            ]
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False
    assert service.prices.count() == 0


@pytest.mark.django_db
def test_update_prices_replaces_existing_prices(authenticated_client, service):
    ServicePrice.objects.create(
        service=service,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount="500.00",
    )
    ServicePrice.objects.create(
        service=service,
        price_type=ServicePrice.PriceType.FULL_DAY,
        amount="900.00",
    )

    response = authenticated_client.patch(
        "/api/service/prices/",
        {
            "prices": [
                {
                    "price_type": ServicePrice.PriceType.NIGHT,
                    "amount": "1200.00",
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert service.prices.count() == 1
    assert service.prices.first().price_type == ServicePrice.PriceType.NIGHT


@pytest.mark.django_db
def test_update_prices_requires_service(authenticated_client):
    response = authenticated_client.patch(
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

    assert response.status_code == 404
    assert response.data["success"] is False