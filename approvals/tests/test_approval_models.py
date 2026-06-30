import pytest
from django.core.exceptions import ValidationError

from accounts.models import TelegramUser
from approvals.models import (
    AdminSettings,
    ContactRequest,
)


@pytest.fixture
def customer():
    return TelegramUser.objects.create(
        telegram_id=80001,
        role=TelegramUser.Role.CUSTOMER,
    )


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=80002,
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.mark.django_db
def test_contact_request_creation(customer, provider):
    request = ContactRequest.objects.create(
        customer=customer,
        provider=provider,
    )

    assert request.status == ContactRequest.Status.PENDING


@pytest.mark.django_db
def test_invalid_status(customer, provider):
    request = ContactRequest(
        customer=customer,
        provider=provider,
        status="invalid_status",
    )

    with pytest.raises(ValidationError):
        request.full_clean()


@pytest.mark.django_db
def test_customer_cannot_request_self(customer):
    request = ContactRequest(
        customer=customer,
        provider=customer,
    )

    with pytest.raises(ValidationError):
        request.full_clean()


@pytest.mark.django_db
def test_singleton_admin_settings():
    settings_one = AdminSettings.get_settings()
    settings_two = AdminSettings.get_settings()

    assert settings_one.pk == settings_two.pk
    assert AdminSettings.objects.count() == 1


@pytest.mark.django_db
def test_default_reset_days():
    settings = AdminSettings.get_settings()

    assert settings.reset_days == 6


@pytest.mark.django_db
def test_maybe_auto_approve_when_enabled(customer, provider):
    from approvals.contact_workflow import maybe_auto_approve_contact_request
    settings = AdminSettings.get_settings()
    settings.auto_approve_requests = True
    settings.save()

    contact_request = ContactRequest.objects.create(
        customer=customer,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    result = maybe_auto_approve_contact_request(contact_request)

    assert result is True
    contact_request.refresh_from_db()
    assert contact_request.status == ContactRequest.Status.AUTO_APPROVED
    assert contact_request.approved_at is not None


@pytest.mark.django_db
def test_maybe_auto_approve_when_disabled(customer, provider):
    from approvals.contact_workflow import maybe_auto_approve_contact_request
    settings = AdminSettings.get_settings()
    settings.auto_approve_requests = False
    settings.save()

    contact_request = ContactRequest.objects.create(
        customer=customer,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    result = maybe_auto_approve_contact_request(contact_request)

    assert result is False
    contact_request.refresh_from_db()
    assert contact_request.status == ContactRequest.Status.PENDING
    assert contact_request.approved_at is None