from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import TelegramUser
from approvals.models import ContactRequest, CustomerSurvey
from services.models import ServiceCategory, ServiceProfile


@pytest.fixture
def customer():
    return TelegramUser.objects.create(
        telegram_id=99001,
        role=TelegramUser.Role.CUSTOMER,
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
    )


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=99002,
        role=TelegramUser.Role.PROVIDER,
        first_name="Provider",
        phone_number="+251911111111",
    )


@pytest.fixture
def contact_request(customer, provider):
    return ContactRequest.objects.create(
        customer=customer,
        provider=provider,
        status=ContactRequest.Status.APPROVED,
        approved_at=timezone.now(),
    )


@pytest.mark.django_db
class TestCustomerSurveyModel:
    def test_create_survey(self, contact_request):
        survey = CustomerSurvey.objects.create(
            contact_request=contact_request,
            sent_at=timezone.now(),
        )
        assert survey.id is not None
        assert survey.response == ""
        assert survey.no_reason == ""

    def test_survey_response_choices(self, contact_request):
        survey = CustomerSurvey.objects.create(
            contact_request=contact_request,
            sent_at=timezone.now(),
            response="yes",
            responded_at=timezone.now(),
        )
        assert survey.response == "yes"

    def test_survey_no_reason_choices(self, contact_request):
        survey = CustomerSurvey.objects.create(
            contact_request=contact_request,
            sent_at=timezone.now(),
            no_reason="price_change",
        )
        assert survey.no_reason == "price_change"

    def test_survey_one_to_one_constraint(self, contact_request):
        CustomerSurvey.objects.create(
            contact_request=contact_request,
            sent_at=timezone.now(),
        )
        with pytest.raises(Exception):
            CustomerSurvey.objects.create(
                contact_request=contact_request,
                sent_at=timezone.now(),
            )
