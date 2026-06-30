import pytest

from bot.models import BotRegistrationSession
from bot.registration_state import RegistrationStateMachine


@pytest.mark.django_db
def test_registration_session_starts_at_select_role():
    session = RegistrationStateMachine.start_or_reset(
        telegram_user_id=123,
        chat_id=456,
    )

    assert session.state == BotRegistrationSession.State.SELECT_ROLE
    assert session.data["role"] == ""
    assert session.data["prices"] == {}
    assert session.data["photos"] == []


@pytest.mark.django_db
def test_provider_role_moves_to_phone_step():
    session = RegistrationStateMachine.start_or_reset(123, 456)

    success, _ = RegistrationStateMachine.set_role(session, "provider")

    session.refresh_from_db()

    assert success is True
    assert session.state == BotRegistrationSession.State.PROVIDER_PHONE
    assert session.data["role"] == "provider"


@pytest.mark.django_db
def test_customer_role_skips_phone_and_moves_to_category():
    session = RegistrationStateMachine.start_or_reset(123, 456)

    success, _ = RegistrationStateMachine.set_role(session, "customer")

    session.refresh_from_db()

    assert success is True
    assert session.state == BotRegistrationSession.State.CATEGORY
    assert session.data["role"] == "customer"


@pytest.mark.django_db
def test_provider_flow_reaches_submit_ready_state():
    session = RegistrationStateMachine.start_or_reset(
        123,
        456,
        telegram_username="provider_user",
    )

    assert RegistrationStateMachine.set_role(session, "provider")[0] is True
    assert RegistrationStateMachine.set_phone_from_contact(
        session,
        {"phone_number": "+251900000000"},
    )[0] is True
    assert RegistrationStateMachine.set_secondary_phone_number(
        session,
        "skip",
    )[0] is True
    assert RegistrationStateMachine.set_category(session, "Electrician")[0] is True
    assert RegistrationStateMachine.set_title(session, "28")[0] is True
    assert RegistrationStateMachine.set_description(
        session,
        "I provide safe electrical repair services.",
    )[0] is True
    assert RegistrationStateMachine.set_location_from_gps(
        session,
        {
            "latitude": 9.010793,
            "longitude": 38.761252,
        },
    )[0] is True
    assert RegistrationStateMachine.set_price(session, "half_day", "500")[0] is True
    assert RegistrationStateMachine.finish_prices(session)[0] is True
    assert RegistrationStateMachine.add_photo(session, "photo_file_id_1")[0] is True
    assert RegistrationStateMachine.finish_photos(session)[0] is True

    session.refresh_from_db()

    assert session.state == BotRegistrationSession.State.SUBMIT

    success, message = RegistrationStateMachine.submit(session)

    session.refresh_from_db()

    assert success is True
    assert "completed" in message.lower()
    assert session.state == BotRegistrationSession.State.COMPLETED


@pytest.mark.django_db
def test_invalid_price_is_rejected():
    session = RegistrationStateMachine.start_or_reset(123, 456)

    success, message = RegistrationStateMachine.set_price(session, "half_day", "-1")

    assert success is False
    assert "greater than zero" in message


@pytest.mark.django_db
def test_provider_age_must_be_numeric():
    session = RegistrationStateMachine.start_or_reset(123, 456)

    success, message = RegistrationStateMachine.set_title(session, "Professional Electrician")

    assert success is False
    assert "Age must be a number" in message


@pytest.mark.django_db
def test_manual_city_location_is_disabled():
    session = RegistrationStateMachine.start_or_reset(123, 456)

    success, message = RegistrationStateMachine.set_location_from_text(session, "Addis Ababa")

    assert success is False
    assert "Manual city entry is disabled" in message


@pytest.mark.django_db
def test_provider_submit_requires_telegram_username():
    session = RegistrationStateMachine.start_or_reset(123, 456)

    assert RegistrationStateMachine.set_role(session, "provider")[0] is True
    assert RegistrationStateMachine.set_phone_from_contact(
        session,
        {"phone_number": "+251900000000"},
    )[0] is True
    assert RegistrationStateMachine.set_secondary_phone_number(session, "skip")[0] is True
    assert RegistrationStateMachine.set_category(session, "Electrician")[0] is True
    assert RegistrationStateMachine.set_title(session, "28")[0] is True
    assert RegistrationStateMachine.set_description(
        session,
        "I provide safe electrical repair services.",
    )[0] is True
    assert RegistrationStateMachine.set_location_from_gps(
        session,
        {
            "latitude": 9.010793,
            "longitude": 38.761252,
        },
    )[0] is True
    assert RegistrationStateMachine.set_price(session, "half_day", "500")[0] is True
    assert RegistrationStateMachine.finish_prices(session)[0] is True
    assert RegistrationStateMachine.add_photo(session, "photo_file_id_1")[0] is True
    assert RegistrationStateMachine.finish_photos(session)[0] is True

    success, message = RegistrationStateMachine.submit(session)

    assert success is False
    assert "Telegram username is required" in message


@pytest.mark.django_db
def test_fourth_photo_is_rejected():
    session = RegistrationStateMachine.start_or_reset(123, 456)

    assert RegistrationStateMachine.add_photo(session, "photo_1")[0] is True
    assert RegistrationStateMachine.add_photo(session, "photo_2")[0] is True
    assert RegistrationStateMachine.add_photo(session, "photo_3")[0] is True

    success, message = RegistrationStateMachine.add_photo(session, "photo_4")

    assert success is False
    assert "Maximum 3 photos" in message
