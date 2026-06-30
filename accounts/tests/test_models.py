import pytest
from django.core.exceptions import ValidationError

from accounts.models import TelegramUser


@pytest.mark.django_db
def test_telegram_user_can_be_created():
    user = TelegramUser.objects.create(
        telegram_id=1001,
        telegram_username="@test_user",
        first_name="Test",
        last_name="User",
        role=TelegramUser.Role.CUSTOMER,
    )

    assert user.telegram_id == 1001
    assert user.telegram_username == "test_user"
    assert user.get_display_name() == "Test User"
    assert user.can_use_marketplace is True


@pytest.mark.django_db
def test_telegram_id_must_be_unique():
    TelegramUser.objects.create(telegram_id=2001)

    with pytest.raises(ValidationError):
        TelegramUser.objects.create(telegram_id=2001)


@pytest.mark.django_db
def test_invalid_role_is_rejected():
    user = TelegramUser(
        telegram_id=3001,
        role="invalid_role",
    )

    with pytest.raises(ValidationError):
        user.full_clean()


@pytest.mark.django_db
def test_telegram_id_must_be_positive():
    user = TelegramUser(telegram_id=-10)

    with pytest.raises(ValidationError):
        user.full_clean()


@pytest.mark.django_db
def test_banned_user_cannot_use_marketplace():
    user = TelegramUser.objects.create(
        telegram_id=4001,
        is_banned=True,
    )

    assert user.can_use_marketplace is False


@pytest.mark.django_db
def test_telegram_user_gps_validation():
    # Only latitude provided -> rejected
    user = TelegramUser(telegram_id=5001, customer_latitude=9.0)
    with pytest.raises(ValidationError):
        user.full_clean()

    # Out of bounds latitude -> rejected
    user = TelegramUser(telegram_id=5002, customer_latitude=95.0, customer_longitude=38.0)
    with pytest.raises(ValidationError):
        user.full_clean()

    # Valid -> allowed
    user = TelegramUser(telegram_id=5003, customer_latitude=9.0, customer_longitude=38.0)
    user.full_clean()
    assert user.has_customer_location is True


@pytest.mark.django_db
def test_telegram_user_ethiopia_gps_warning(monkeypatch):
    import logging
    warnings_logged = []

    class FakeLogger:
        def warning(self, msg, *args, **kwargs):
            warnings_logged.append((msg, args))
        def info(self, *args, **kwargs):
            pass
        def error(self, *args, **kwargs):
            pass

    real_get_logger = logging.getLogger
    monkeypatch.setattr("logging.getLogger", lambda name=None: FakeLogger() if name == "marketplace" else real_get_logger(name))

    user = TelegramUser(
        telegram_id=6001,
        customer_latitude=45.0,  # Outside Ethiopia
        customer_longitude=38.0,
    )
    user.full_clean()
    assert len(warnings_logged) == 1
    assert "outside Ethiopia's bounding box" in warnings_logged[0][0]


@pytest.mark.django_db
def test_telegram_user_update_last_interaction():
    user = TelegramUser.objects.create(telegram_id=7001)
    assert user.last_interaction_at is None

    user.update_last_interaction(save=True)
    assert user.last_interaction_at is not None

    # Verify directly from db
    db_user = TelegramUser.objects.get(telegram_id=7001)
    assert db_user.last_interaction_at is not None
