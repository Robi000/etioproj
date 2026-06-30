import pytest

from bot.models import BotRegistrationSession
from bot.registration_state import RegistrationStateMachine


@pytest.mark.django_db
def test_start_or_reset_stores_telegram_username_and_secondary_phone_slot():
    session = RegistrationStateMachine.start_or_reset(
        telegram_user_id=700001,
        chat_id=800001,
        telegram_username="provider_user",
    )

    assert session.state == BotRegistrationSession.State.SELECT_ROLE
    assert session.data["telegram_username"] == "provider_user"
    assert session.data["secondary_phone_number"] == ""


@pytest.mark.django_db
def test_age_is_numeric_and_stored_in_existing_title_field():
    session = RegistrationStateMachine.start_or_reset(700002, 800002)

    success, message = RegistrationStateMachine.set_title(session, "31")

    session.refresh_from_db()

    assert success is True
    assert "Age saved" in message
    assert session.data["title"] == "31"
    assert session.state == BotRegistrationSession.State.DESCRIPTION


@pytest.mark.django_db
def test_non_numeric_age_is_rejected():
    session = RegistrationStateMachine.start_or_reset(700003, 800003)

    success, message = RegistrationStateMachine.set_title(session, "thirty one")

    assert success is False
    assert "Age must be a number" in message


@pytest.mark.django_db
def test_underage_provider_registration_clears_saved_draft():
    session = RegistrationStateMachine.start_or_reset(700006, 800006)
    data = session.data
    data.update(
        {
            "role": "provider",
            "phone_number": "+251911111111",
            "category": "Electrician",
        }
    )
    session.data = data
    session.save(update_fields=["data", "updated_at"])

    success, message = RegistrationStateMachine.set_title(session, "17")

    session.refresh_from_db()

    assert success is False
    assert "18 or older" in message
    assert session.state == BotRegistrationSession.State.CANCELLED
    assert session.data == {"underage_rejected": True}


@pytest.mark.django_db
def test_manual_city_text_is_disabled():
    session = RegistrationStateMachine.start_or_reset(700004, 800004)

    success, message = RegistrationStateMachine.set_location_from_text(
        session,
        "Addis Ababa",
    )

    assert success is False
    assert "Manual city entry is disabled" in message


@pytest.mark.django_db
def test_secondary_phone_skip_button_text_is_accepted():
    session = RegistrationStateMachine.start_or_reset(700005, 800005)

    success, message = RegistrationStateMachine.set_secondary_phone_number(
        session,
        "Skip Secondary Phone",
    )

    session.refresh_from_db()

    assert success is True
    assert "skipped" in message.lower()
    assert session.data["secondary_phone_number"] == ""
    assert session.state == BotRegistrationSession.State.CATEGORY
