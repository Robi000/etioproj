import pytest
from django.core.exceptions import ValidationError

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServicePrice, ServiceProfile


@pytest.fixture
def provider_user():
    return TelegramUser.objects.create(
        telegram_id=11001,
        telegram_username="price_provider",
        first_name="Price",
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def category():
    return ServiceCategory.objects.create(name="Plumber")


@pytest.fixture
def service_profile(provider_user, category):
    return ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Professional Plumbing",
        description="Plumbing installation and repair service.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )


@pytest.mark.django_db
def test_service_price_can_be_created(service_profile):
    price = ServicePrice.objects.create(
        service=service_profile,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount="500.00",
    )

    assert price.service == service_profile
    assert price.price_type == ServicePrice.PriceType.HALF_DAY
    assert str(price.amount) == "500.00"


@pytest.mark.django_db
def test_allowed_price_types_are_supported(service_profile):
    ServicePrice.objects.create(
        service=service_profile,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount="500.00",
    )
    ServicePrice.objects.create(
        service=service_profile,
        price_type=ServicePrice.PriceType.FULL_DAY,
        amount="900.00",
    )
    ServicePrice.objects.create(
        service=service_profile,
        price_type=ServicePrice.PriceType.NIGHT,
        amount="1200.00",
    )

    assert service_profile.prices.count() == 3


@pytest.mark.django_db
def test_invalid_price_type_is_rejected(service_profile):
    price = ServicePrice(
        service=service_profile,
        price_type="weekly",
        amount="1000.00",
    )

    with pytest.raises(ValidationError):
        price.full_clean()


@pytest.mark.django_db
def test_price_amount_must_be_positive(service_profile):
    price = ServicePrice(
        service=service_profile,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount="0.00",
    )

    with pytest.raises(ValidationError):
        price.full_clean()


@pytest.mark.django_db
def test_negative_price_amount_is_rejected(service_profile):
    price = ServicePrice(
        service=service_profile,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount="-100.00",
    )

    with pytest.raises(ValidationError):
        price.full_clean()


@pytest.mark.django_db
def test_service_and_price_type_must_be_unique(service_profile):
    ServicePrice.objects.create(
        service=service_profile,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount="500.00",
    )

    with pytest.raises(ValidationError):
        ServicePrice.objects.create(
            service=service_profile,
            price_type=ServicePrice.PriceType.HALF_DAY,
            amount="600.00",
        )


@pytest.mark.django_db
def test_service_profile_has_at_least_one_price_helper(service_profile):
    assert service_profile.has_at_least_one_price() is False

    ServicePrice.objects.create(
        service=service_profile,
        price_type=ServicePrice.PriceType.NIGHT,
        amount="1200.00",
    )

    assert service_profile.has_at_least_one_price() is True
