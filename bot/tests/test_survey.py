from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import TelegramUser
from approvals.models import ContactRequest, CustomerSurvey
from bot.handler_modules.survey import can_handle_callback, handle_callback
from bot.handler_modules.utils import TelegramUpdateContext
from bot.services import TelegramBotService
from services.models import ServiceCategory, ServiceProfile


class FakeBot:
    def __init__(self):
        self.sent_messages = []
        self.answered_callbacks = []

    def send_text(self, chat_id, text, reply_markup=None):
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
        })
        return True

    def answer_callback(self, callback_query_id, text):
        self.answered_callbacks.append({
            "callback_query_id": callback_query_id,
            "text": text,
        })
        return True


def make_context(telegram_user_id=1, chat_id=100, update_id=1000):
    return TelegramUpdateContext(
        update_id=update_id,
        chat_id=chat_id,
        telegram_user_id=telegram_user_id,
        username="test_user",
        first_name="Test",
        message=None,
        callback_query={"id": "cq1"},
    )


@pytest.fixture
def customer():
    return TelegramUser.objects.create(
        telegram_id=1,
        role=TelegramUser.Role.CUSTOMER,
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
    )


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=2,
        role=TelegramUser.Role.PROVIDER,
        first_name="Provider",
        phone_number="+251911111111",
    )


@pytest.fixture
def approved_contact(customer, provider):
    return ContactRequest.objects.create(
        customer=customer,
        provider=provider,
        status=ContactRequest.Status.APPROVED,
        approved_at=timezone.now() - timezone.timedelta(days=3),
    )


@pytest.mark.django_db
class TestSurveyHandler:
    def test_can_handle_callback(self):
        assert can_handle_callback("survey:yes:1") is True
        assert can_handle_callback("survey:no:1") is True
        assert can_handle_callback("survey:reason:price_change:1") is True
        assert can_handle_callback("contact:accept:1") is False
        assert can_handle_callback("") is False

    def test_survey_yes_response(self, approved_contact):
        bot = FakeBot()
        survey = CustomerSurvey.objects.create(
            contact_request=approved_contact,
            sent_at=timezone.now(),
        )
        context = make_context(telegram_user_id=1)

        result = handle_callback(bot, context, f"survey:yes:{approved_contact.id}")

        assert result.handled is True
        assert result.route == "survey.yes"

        survey.refresh_from_db()
        assert survey.response == "yes"
        assert survey.responded_at is not None
        assert len(bot.sent_messages) >= 1
        assert "Thank you" in bot.sent_messages[-1]["text"]

    def test_survey_no_response(self, approved_contact):
        bot = FakeBot()
        survey = CustomerSurvey.objects.create(
            contact_request=approved_contact,
            sent_at=timezone.now(),
        )
        context = make_context(telegram_user_id=1)

        result = handle_callback(bot, context, f"survey:no:{approved_contact.id}")

        assert result.handled is True
        assert result.route == "survey.no"

        survey.refresh_from_db()
        assert survey.response == "no"
        assert survey.responded_at is not None

        assert len(bot.sent_messages) >= 1
        assert "Sorry to hear" in bot.sent_messages[-1]["text"]

    def test_survey_reason_callback(self, approved_contact):
        bot = FakeBot()
        survey = CustomerSurvey.objects.create(
            contact_request=approved_contact,
            sent_at=timezone.now(),
            response="no",
            responded_at=timezone.now(),
        )
        context = make_context(telegram_user_id=1)

        result = handle_callback(
            bot, context, f"survey:reason:price_change:{approved_contact.id}"
        )

        assert result.handled is True
        assert result.route == "survey.reason"

        survey.refresh_from_db()
        assert survey.no_reason == "price_change"
        assert len(bot.sent_messages) >= 1
        assert "Thank you" in bot.sent_messages[-1]["text"]

    def test_survey_not_found(self, approved_contact):
        bot = FakeBot()
        context = make_context(telegram_user_id=1)

        result = handle_callback(bot, context, "survey:yes:99999")

        assert result.handled is False
        assert "survey.callback.not_found" == result.route
        assert any("not found" in m["text"].lower() for m in bot.sent_messages)

    def test_survey_invalid_callback_format(self):
        bot = FakeBot()
        context = make_context(telegram_user_id=1)

        result = handle_callback(bot, context, "survey:invalid:1")

        assert result.handled is False
        assert "invalid" in result.route

    def test_survey_yes_idempotent(self, approved_contact):
        bot = FakeBot()
        survey = CustomerSurvey.objects.create(
            contact_request=approved_contact,
            sent_at=timezone.now(),
        )
        context = make_context(telegram_user_id=1)

        first = handle_callback(bot, context, f"survey:yes:{approved_contact.id}")
        assert first.handled is True
        assert first.route == "survey.yes"

        bot.sent_messages.clear()

        second = handle_callback(bot, context, f"survey:yes:{approved_contact.id}")
        assert second.handled is True
        assert second.route == "survey.yes"

        survey.refresh_from_db()
        assert survey.response == "yes"
        assert survey.responded_at is not None
        assert "Thank you" in bot.sent_messages[-1]["text"]

    def test_survey_no_idempotent(self, approved_contact):
        bot = FakeBot()
        survey = CustomerSurvey.objects.create(
            contact_request=approved_contact,
            sent_at=timezone.now(),
        )
        context = make_context(telegram_user_id=1)

        first = handle_callback(bot, context, f"survey:no:{approved_contact.id}")
        assert first.handled is True

        bot.sent_messages.clear()

        second = handle_callback(bot, context, f"survey:no:{approved_contact.id}")
        assert second.handled is True

        survey.refresh_from_db()
        assert survey.response == "no"
        assert "Sorry to hear" in bot.sent_messages[-1]["text"]

    def test_survey_reason_idempotent(self, approved_contact):
        bot = FakeBot()
        survey = CustomerSurvey.objects.create(
            contact_request=approved_contact,
            sent_at=timezone.now(),
            response="no",
            responded_at=timezone.now(),
        )
        context = make_context(telegram_user_id=1)

        first = handle_callback(
            bot, context, f"survey:reason:price_change:{approved_contact.id}"
        )
        assert first.handled is True
        assert first.route == "survey.reason"

        bot.sent_messages.clear()

        second = handle_callback(
            bot, context, f"survey:reason:price_change:{approved_contact.id}"
        )
        assert second.handled is True
        assert second.route == "survey.reason"

        survey.refresh_from_db()
        assert survey.no_reason == "price_change"
        assert "Thank you" in bot.sent_messages[-1]["text"]
