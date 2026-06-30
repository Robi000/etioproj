from unittest.mock import patch

import pytest
from django.utils import timezone

from accounts.models import TelegramUser
from approvals.models import ContactRequest
from bot.handler_modules.contact_requests import _evaluate_and_apply_penalty
from services.models import PhotoChangeRequest, ServiceCategory, ServiceProfile


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=95001,
        role=TelegramUser.Role.PROVIDER,
        first_name="PenaltyProvider",
        phone_number="+251911111111",
    )


@pytest.fixture
def category():
    return ServiceCategory.objects.create(name="Penalty Cat")


@pytest.fixture
def service(provider, category):
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="Penalty Service",
        description="Test",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
        denial_count=0,
        penalty_count=0,
    )


def make_contact(provider, customer_telegram_id, status=ContactRequest.Status.APPROVED, service=None):
    customer = TelegramUser.objects.create(
        telegram_id=customer_telegram_id,
        role=TelegramUser.Role.CUSTOMER,
    )
    kwargs = dict(
        customer=customer,
        provider=provider,
        status=status,
        approved_at=timezone.now() - timezone.timedelta(days=1),
    )
    if service is not None:
        kwargs["service"] = service
    return ContactRequest.objects.create(**kwargs)


@pytest.mark.django_db
class TestPenaltyEdgeCases:
    def test_zero_total_requests_no_penalty(self, service, provider):
        service.denial_count = 0
        service.penalty_count = 0
        service.save()

        _evaluate_and_apply_penalty(service)

        service.refresh_from_db()
        assert service.penalty_count == 0
        assert service.penalty_until is None
        assert service.visibility_status == ServiceProfile.VisibilityStatus.ON

    def test_nine_requests_nine_denials_no_penalty_below_grace(self, service, provider):
        for i in range(9):
            make_contact(provider, 95100 + i)
        service.denial_count = 9
        service.penalty_count = 0
        service.save()

        _evaluate_and_apply_penalty(service)

        service.refresh_from_db()
        assert service.penalty_count == 0
        assert service.penalty_until is None

    def test_ten_requests_seven_denials_no_penalty_below_threshold(self, service, provider):
        for i in range(10):
            make_contact(provider, 95200 + i)
        service.denial_count = 7
        service.penalty_count = 0
        service.save()

        _evaluate_and_apply_penalty(service)

        service.refresh_from_db()
        assert service.penalty_count == 0
        assert service.penalty_until is None

    def test_ten_requests_eight_denials_penalty_applied(self, service, provider):
        for i in range(10):
            make_contact(provider, 95300 + i)
        service.denial_count = 8
        service.penalty_count = 0
        service.save()

        _evaluate_and_apply_penalty(service)

        service.refresh_from_db()
        assert service.penalty_count == 1
        assert service.penalty_until is not None
        assert service.visibility_status == ServiceProfile.VisibilityStatus.OFF

    def test_first_penalty_seven_days(self, service, provider):
        for i in range(10):
            make_contact(provider, 95400 + i)
        service.denial_count = 8
        service.penalty_count = 0
        service.save()

        _evaluate_and_apply_penalty(service)

        service.refresh_from_db()
        expected = timezone.now() + timezone.timedelta(days=7)
        diff = abs((service.penalty_until - expected).total_seconds())
        assert diff < 10

    def test_second_penalty_fifteen_days(self, service, provider):
        for i in range(10):
            make_contact(provider, 95500 + i)
        service.denial_count = 8
        service.penalty_count = 1
        service.save()

        _evaluate_and_apply_penalty(service)

        service.refresh_from_db()
        assert service.penalty_count == 2
        expected = timezone.now() + timezone.timedelta(days=15)
        diff = abs((service.penalty_until - expected).total_seconds())
        assert diff < 10

    def test_reject_contact_request_increments_denial_and_evaluates_penalty(self, service, provider):
        from bot.handler_modules.contact_requests import reject_contact_request
        from bot.services import TelegramBotService
        from bot.handler_modules.utils import TelegramUpdateContext

        for i in range(9):
            make_contact(provider, 95600 + i, service=service)
        service.denial_count = 7
        service.penalty_count = 0
        service.save()

        contact = make_contact(
            provider, 95700,
            status=ContactRequest.Status.PENDING,
            service=service,
        )

        bot = TelegramBotService()
        context = TelegramUpdateContext(
            update_id=10000,
            chat_id=provider.telegram_id,
            telegram_user_id=provider.telegram_id,
            username="test",
            first_name="Test",
            message=None,
            callback_query={"id": "cq1"},
        )

        with patch.object(bot, "send_text", return_value=True):
            result = reject_contact_request(bot, context, contact)

        assert result.handled is True
        service.refresh_from_db()
        assert service.denial_count == 8
        assert service.penalty_count == 1
