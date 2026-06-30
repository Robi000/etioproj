from decimal import Decimal

import pytest

from accounts.models import TelegramUser
from bot.models import BotRegistrationSession
from bot.registration_submitter import BotRegistrationSubmitter
from services.models import ServicePhoto, ServicePrice, ServiceProfile


@pytest.fixture
def completed_session():
    return BotRegistrationSession.objects.create(
        telegram_user_id=777001,
        chat_id=888001,
        state=BotRegistrationSession.State.SUBMIT,
        data={
            "role": TelegramUser.Role.PROVIDER,
            "telegram_username": "provider_submitter",
            "phone_number": "+251911111111",
            "secondary_phone_number": "+251922222222",
            "category": "Electrician",
            "title": "28",
            "description": "I provide professional electrical repair services.",
            "location": {
                "source": "gps",
                "city_text": "",
                "latitude": 9.03,
                "longitude": 38.74,
            },
            "prices": {
                "half_day": "500",
                "full_day": "900",
            },
            "photos": [
                {
                    "telegram_file_id": "photo_file_1",
                    "order_index": 1,
                }
            ],
        },
    )


@pytest.mark.django_db
def test_submit_creates_pending_service(completed_session):
    result = BotRegistrationSubmitter.submit(completed_session)

    completed_session.refresh_from_db()

    assert result.success is True
    assert result.service_id is not None
    assert completed_session.state == BotRegistrationSession.State.COMPLETED

    user = TelegramUser.objects.get(telegram_id=777001)
    service = ServiceProfile.objects.get(provider=user)

    assert user.telegram_username == "provider_submitter"
    assert user.phone_number == "+251911111111"
    assert user.secondary_phone_number == "+251922222222"
    assert service.approval_status == ServiceProfile.ApprovalStatus.PENDING
    assert service.visibility_status == ServiceProfile.VisibilityStatus.ON
    assert service.title == "28"
    assert service.latitude == Decimal("9.030000")
    assert service.longitude == Decimal("38.740000")
    assert service.prices.count() == 2
    assert service.photos.count() == 1


@pytest.mark.django_db
def test_submit_rejects_missing_username(completed_session):
    data = completed_session.data
    data["telegram_username"] = ""
    completed_session.data = data
    completed_session.save()

    result = BotRegistrationSubmitter.submit(completed_session)

    assert result.success is False
    assert "telegram_username" in result.message
    assert ServiceProfile.objects.count() == 0


@pytest.mark.django_db
def test_submit_rejects_duplicate_provider_service(completed_session):
    first_result = BotRegistrationSubmitter.submit(completed_session)
    second_result = BotRegistrationSubmitter.submit(completed_session)

    assert first_result.success is True
    assert second_result.success is False
    assert second_result.service_id == first_result.service_id
    assert ServiceProfile.objects.count() == 1


@pytest.mark.django_db
def test_submit_creates_price_and_photo_rows(completed_session):
    result = BotRegistrationSubmitter.submit(completed_session)

    assert result.success is True
    assert ServicePrice.objects.count() == 2
    assert ServicePhoto.objects.count() == 1
    assert ServicePrice.objects.get(price_type=ServicePrice.PriceType.HALF_DAY).amount == Decimal("500.00")
    assert ServicePhoto.objects.get().order_index == 1


@pytest.mark.django_db
def test_submit_rejects_invalid_gps_coordinate(completed_session):
    data = completed_session.data
    data["location"]["latitude"] = "not-a-coordinate"
    completed_session.data = data
    completed_session.save()

    result = BotRegistrationSubmitter.submit(completed_session)

    assert result.success is False
    assert "GPS latitude and longitude" in result.message
    assert ServiceProfile.objects.count() == 0
