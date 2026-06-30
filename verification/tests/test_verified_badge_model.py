import pytest
from django.core.exceptions import ValidationError

from accounts.models import TelegramUser
from services.models import (
    ServiceCategory,
    ServiceProfile,
)
from verification.models import VerifiedBadge


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=91001,
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Verified Test Category"
    )


@pytest.fixture
def approved_service(provider, category):
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="Approved Service",
        description="Description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
    )


@pytest.mark.django_db
def test_manual_badge_creation(approved_service):
    badge = VerifiedBadge.objects.create(
        service=approved_service,
        badge_type=VerifiedBadge.BadgeType.MANUAL,
    )

    assert badge.badge_type == VerifiedBadge.BadgeType.MANUAL


@pytest.mark.django_db
def test_invalid_badge_type(approved_service):
    badge = VerifiedBadge(
        service=approved_service,
        badge_type="invalid",
    )

    with pytest.raises(ValidationError):
        badge.full_clean()