import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import TelegramUser
from services.models import (
    ServiceCategory,
    ServiceProfile,
)
from swipes.models import SwipeHistory


@pytest.fixture
def customer():
    return TelegramUser.objects.create(
        telegram_id=70001,
        role=TelegramUser.Role.CUSTOMER,
    )


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=70002,
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Tutor"
    )


@pytest.fixture
def service(provider, category):
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="Math Tutor",
        description="Math tutoring service",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )


@pytest.mark.django_db
def test_swipe_history_creation(customer, service):
    swipe = SwipeHistory.objects.create(
        customer=customer,
        service=service,
        swipe_status=SwipeHistory.SwipeStatus.LIKED,
    )

    assert swipe.swipe_status == SwipeHistory.SwipeStatus.LIKED


@pytest.mark.django_db
def test_invalid_swipe_status(customer, service):
    swipe = SwipeHistory(
        customer=customer,
        service=service,
        swipe_status="invalid_status",
    )

    with pytest.raises(ValidationError):
        swipe.full_clean()


@pytest.mark.django_db
def test_reset_date_is_six_days(customer, service):
    swipe = SwipeHistory.objects.create(
        customer=customer,
        service=service,
        swipe_status=SwipeHistory.SwipeStatus.SEEN,
    )

    delta = swipe.reset_at - timezone.now()

    assert 5 <= delta.days <= 6


@pytest.mark.django_db
def test_banned_customer_cannot_swipe(customer, service):
    customer.is_banned = True
    customer.save()

    swipe = SwipeHistory(
        customer=customer,
        service=service,
        swipe_status=SwipeHistory.SwipeStatus.LIKED,
    )

    with pytest.raises(ValidationError):
        swipe.full_clean()