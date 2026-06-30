import pytest
from django.core.exceptions import ValidationError

from accounts.models import TelegramUser
from moderation.models import Report


@pytest.fixture
def reporter():
    return TelegramUser.objects.create(
        telegram_id=90001,
        role=TelegramUser.Role.CUSTOMER,
    )


@pytest.fixture
def reported():
    return TelegramUser.objects.create(
        telegram_id=90002,
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.mark.django_db
def test_report_creation(reporter, reported):
    report = Report.objects.create(
        reporter=reporter,
        reported_user=reported,
        reason="Spam",
    )

    assert report.status == Report.Status.PENDING


@pytest.mark.django_db
def test_invalid_report_status(reporter, reported):
    report = Report(
        reporter=reporter,
        reported_user=reported,
        reason="Spam",
        status="invalid",
    )

    with pytest.raises(ValidationError):
        report.full_clean()


@pytest.mark.django_db
def test_user_cannot_report_self(reporter):
    report = Report(
        reporter=reporter,
        reported_user=reporter,
        reason="Spam",
    )

    with pytest.raises(ValidationError):
        report.full_clean()