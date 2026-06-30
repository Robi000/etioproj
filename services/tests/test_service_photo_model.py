import pytest
from django.core.exceptions import ValidationError

from accounts.models import TelegramUser
from services.models import (
    ServiceCategory,
    ServiceProfile,
    ServicePhoto,
)


@pytest.fixture
def provider_user():
    return TelegramUser.objects.create(
        telegram_id=50001,
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Mechanic"
    )


@pytest.fixture
def service(provider_user, category):
    return ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Mechanic Service",
        description="Mechanic description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )


@pytest.mark.django_db
def test_service_can_have_three_photos(service):
    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_1",
        order_index=1,
    )

    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_2",
        order_index=2,
    )

    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_3",
        order_index=3,
    )

    assert service.photos.count() == 3


@pytest.mark.django_db
def test_fourth_photo_is_rejected(service):
    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_1",
        order_index=1,
    )

    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_2",
        order_index=2,
    )

    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_3",
        order_index=3,
    )

    with pytest.raises(ValidationError):
        ServicePhoto.objects.create(
            service=service,
            telegram_file_id="file_4",
            order_index=4,
        )


@pytest.mark.django_db
def test_service_photo_helpers(service):
    assert service.has_minimum_photos() is False

    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_1",
        order_index=1,
    )

    assert service.has_minimum_photos() is True
    assert service.can_add_photo() is True

    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_2",
        order_index=2,
    )

    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="file_3",
        order_index=3,
    )

    assert service.can_add_photo() is False