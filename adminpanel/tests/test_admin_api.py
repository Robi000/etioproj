import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from approvals.models import AdminSettings, ContactRequest
from bot.services import TelegramBotService
from services.models import ServiceCategory, ServiceProfile


@pytest.fixture
def admin_telegram_user():
    return TelegramUser.objects.create(
        telegram_id=99001,
        role=TelegramUser.Role.ADMIN,
        first_name="Admin",
    )


@pytest.fixture
def normal_telegram_user():
    return TelegramUser.objects.create(
        telegram_id=99002,
        role=TelegramUser.Role.CUSTOMER,
    )


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=99003,
        role=TelegramUser.Role.PROVIDER,
        phone_number="+251922222222",
    )


@pytest.fixture
def admin_auth_user(admin_telegram_user):
    return User.objects.create_user(
        username=f"telegram_{admin_telegram_user.telegram_id}",
    )


@pytest.fixture
def normal_auth_user(normal_telegram_user):
    return User.objects.create_user(
        username=f"telegram_{normal_telegram_user.telegram_id}",
    )


@pytest.fixture
def admin_token(admin_auth_user):
    token, _ = Token.objects.get_or_create(user=admin_auth_user)
    return token


@pytest.fixture
def normal_token(normal_auth_user):
    token, _ = Token.objects.get_or_create(user=normal_auth_user)
    return token


@pytest.fixture
def admin_client(api_client, admin_token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {admin_token.key}"
    )
    return api_client


@pytest.fixture
def normal_client(api_client, normal_token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {normal_token.key}"
    )
    return api_client


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Admin API Category"
    )


@pytest.fixture
def pending_service(provider, category):
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="Pending Service",
        description="Pending description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.PENDING,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )


@pytest.mark.django_db
def test_non_admin_cannot_access_admin_services(normal_client):
    response = normal_client.get("/api/admin/services/pending/")

    assert response.status_code == 403
    assert response.data["success"] is False


@pytest.mark.django_db
def test_admin_can_list_pending_services(admin_client, pending_service):
    response = admin_client.get("/api/admin/services/pending/")

    assert response.status_code == 200
    assert response.data["success"] is True
    assert len(response.data["services"]) == 1
    assert response.data["services"][0]["id"] == pending_service.id


@pytest.mark.django_db
def test_admin_can_approve_service(
    admin_client,
    pending_service,
    admin_telegram_user,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    queued_notifications = []
    monkeypatch.setattr(
        "adminpanel.views.queue_service_status_notification",
        lambda service_id, event: queued_notifications.append((service_id, event)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(
            "/api/admin/service/approve/",
            {
                "service_id": pending_service.id,
            },
            format="json",
        )

    pending_service.refresh_from_db()

    assert response.status_code == 200
    assert response.data["success"] is True
    assert pending_service.approval_status == ServiceProfile.ApprovalStatus.APPROVED
    assert pending_service.approved_by == admin_telegram_user
    assert pending_service.approved_at is not None
    assert queued_notifications == [
        (pending_service.id, ServiceProfile.ApprovalStatus.APPROVED)
    ]


@pytest.mark.django_db
def test_admin_can_reject_service(
    admin_client,
    pending_service,
    admin_telegram_user,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    rejection_calls = []
    monkeypatch.setattr(
        "adminpanel.views.queue_service_rejection_with_reason",
        lambda provider_id, reason: rejection_calls.append((provider_id, reason)),
    )

    provider = pending_service.provider

    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(
            "/api/admin/service/reject/",
            {
                "service_id": pending_service.id,
                "rejection_reason": "Violates platform terms of service.",
            },
            format="json",
        )

    assert response.status_code == 200
    assert response.data["success"] is True

    # Service profile and related data should be deleted
    from services.models import ServicePhoto, ServicePrice
    assert ServiceProfile.objects.filter(id=pending_service.id).exists() is False
    assert ServicePhoto.objects.filter(service=pending_service).exists() is False
    assert ServicePrice.objects.filter(service=pending_service).exists() is False

    # Provider role reset to CUSTOMER
    provider.refresh_from_db()
    assert provider.role == TelegramUser.Role.CUSTOMER

    # Rejection notification queued with correct provider id and reason
    assert len(rejection_calls) == 1
    assert rejection_calls[0] == (provider.telegram_id, "Violates platform terms of service.")


@pytest.mark.django_db
def test_admin_can_list_pending_contacts(
    admin_client,
    normal_telegram_user,
    provider,
):
    contact_request = ContactRequest.objects.create(
        customer=normal_telegram_user,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    response = admin_client.get("/api/admin/contacts/pending/")

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["contact_requests"][0]["id"] == contact_request.id


@pytest.mark.django_db
def test_admin_can_approve_contact(
    admin_client,
    normal_telegram_user,
    provider,
    admin_telegram_user,
):
    contact_request = ContactRequest.objects.create(
        customer=normal_telegram_user,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    response = admin_client.post(
        "/api/admin/contact/approve/",
        {
            "contact_request_id": contact_request.id,
        },
        format="json",
    )

    contact_request.refresh_from_db()

    assert response.status_code == 200
    assert contact_request.status == ContactRequest.Status.APPROVED
    assert contact_request.approved_by == admin_telegram_user
    assert contact_request.approved_at is not None


@pytest.mark.django_db
def test_admin_can_reject_contact(
    admin_client,
    normal_telegram_user,
    provider,
    admin_telegram_user,
):
    contact_request = ContactRequest.objects.create(
        customer=normal_telegram_user,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    response = admin_client.post(
        "/api/admin/contact/reject/",
        {
            "contact_request_id": contact_request.id,
        },
        format="json",
    )

    contact_request.refresh_from_db()

    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_can_list_pending_contacts(
    admin_client,
    normal_telegram_user,
    provider,
):
    contact_request = ContactRequest.objects.create(
        customer=normal_telegram_user,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    response = admin_client.get("/api/admin/contacts/pending/")

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["contact_requests"][0]["id"] == contact_request.id


@pytest.mark.django_db
def test_admin_can_approve_contact(
    admin_client,
    normal_telegram_user,
    provider,
    admin_telegram_user,
):
    contact_request = ContactRequest.objects.create(
        customer=normal_telegram_user,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    response = admin_client.post(
        "/api/admin/contact/approve/",
        {
            "contact_request_id": contact_request.id,
        },
        format="json",
    )

    contact_request.refresh_from_db()

    assert response.status_code == 200
    assert contact_request.status == ContactRequest.Status.APPROVED
    assert contact_request.approved_by == admin_telegram_user
    assert contact_request.approved_at is not None


@pytest.mark.django_db
def test_admin_can_reject_contact(
    admin_client,
    normal_telegram_user,
    provider,
    admin_telegram_user,
):
    contact_request = ContactRequest.objects.create(
        customer=normal_telegram_user,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )

    response = admin_client.post(
        "/api/admin/contact/reject/",
        {
            "contact_request_id": contact_request.id,
        },
        format="json",
    )

    contact_request.refresh_from_db()

    assert response.status_code == 200
    assert contact_request.status == ContactRequest.Status.REJECTED
    assert contact_request.approved_by == admin_telegram_user
    assert contact_request.approved_at is None


@pytest.mark.django_db
def test_admin_can_update_settings(admin_client):
    response = admin_client.patch(
        "/api/admin/settings/",
        {
            "auto_approve_requests": True,
            "reset_days": 7,
            "default_radius": 15,
        },
        format="json",
    )

    settings = AdminSettings.get_settings()

    assert response.status_code == 200
    assert response.data["success"] is True
    assert settings.auto_approve_requests is True
    assert settings.reset_days == 7
    assert settings.default_radius == 15


from django.test import Client

@pytest.mark.django_db
def test_dashboard_access_for_superuser_without_telegram_user():
    # Create superuser without telegram_ prefix in username (meaning no linked TelegramUser)
    superuser = User.objects.create_superuser(
        username="django_admin",
        password="adminpassword",
    )
    client = Client()
    client.force_login(superuser)
    
    response = client.get("/dashboard/admin/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_dashboard_actions_without_telegram_user(monkeypatch, pending_service, normal_telegram_user, provider):
    superuser = User.objects.create_superuser(
        username="django_admin",
    )
    client = Client()
    client.force_login(superuser)
    
    # Mock logger directly on views to verify warning event
    warnings_logged = []
    class FakeLogger:
        def warning(self, msg, *args, **kwargs):
            warnings_logged.append((msg, args))
        def info(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass
        
    monkeypatch.setattr("adminpanel.views.logger", FakeLogger())

    # 1. Approve Service
    response = client.post(f"/dashboard/admin/service/{pending_service.id}/approve/")
    assert response.status_code == 302 # Redirects back to dashboard
    pending_service.refresh_from_db()
    assert pending_service.approval_status == ServiceProfile.ApprovalStatus.APPROVED
    assert pending_service.approved_by is None
    assert any("admin_action_no_telegram_user" in w[0] for w in warnings_logged)

    # Reset warning list
    warnings_logged.clear()

    # 2. Approve Contact
    contact_request = ContactRequest.objects.create(
        customer=normal_telegram_user,
        provider=provider,
        status=ContactRequest.Status.PENDING,
    )
    response = client.post(f"/dashboard/admin/contact/{contact_request.id}/approve/")
    assert response.status_code == 302
    contact_request.refresh_from_db()
    assert contact_request.status == ContactRequest.Status.APPROVED
    assert contact_request.approved_by is None
    assert any("admin_action_no_telegram_user" in w[0] for w in warnings_logged)


@pytest.mark.django_db
def test_reject_service_reason_too_short(admin_client, pending_service):
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": "Short"},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["success"] is False


@pytest.mark.django_db
def test_reject_service_reason_blank(admin_client, pending_service):
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": ""},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["success"] is False


@pytest.mark.django_db
def test_reject_service_reason_whitespace_only(admin_client, pending_service):
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": "     "},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_reject_service_reason_exactly_10_chars(admin_client, pending_service, monkeypatch):
    monkeypatch.setattr(
        "adminpanel.views.queue_service_rejection_with_reason",
        lambda provider_id, reason: None,
    )
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": "1234567890"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["success"] is True


@pytest.mark.django_db
def test_reject_service_reason_at_max_length(admin_client, pending_service, monkeypatch):
    monkeypatch.setattr(
        "adminpanel.views.queue_service_rejection_with_reason",
        lambda provider_id, reason: None,
    )
    reason = "a" * 1000
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": reason},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["success"] is True


@pytest.mark.django_db
def test_reject_service_reason_over_1000_chars(admin_client, pending_service):
    reason = "a" * 1001
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": reason},
        format="json",
    )
    # Serializer max_length=1000 should catch it
    assert response.status_code == 400


@pytest.mark.django_db
def test_reject_service_not_found(admin_client):
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": 99999, "rejection_reason": "Valid rejection reason here."},
        format="json",
    )
    assert response.status_code == 404
    assert response.data["success"] is False


@pytest.mark.django_db
def test_reject_service_non_admin(normal_client, pending_service):
    response = normal_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": "Valid rejection reason here."},
        format="json",
    )
    assert response.status_code == 403
    assert response.data["success"] is False


@pytest.mark.django_db
def test_reject_service_missing_service_id(admin_client):
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"rejection_reason": "Valid rejection reason here."},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_reject_service_already_approved(admin_client, pending_service, monkeypatch):
    pending_service.approval_status = ServiceProfile.ApprovalStatus.APPROVED
    pending_service.save()
    monkeypatch.setattr(
        "adminpanel.views.queue_service_rejection_with_reason",
        lambda provider_id, reason: None,
    )
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": "This is a valid reason for rejection."},
        format="json",
    )
    # View doesn't check approval_status; it deletes regardless
    assert response.status_code == 200
    assert response.data["success"] is True


@pytest.mark.django_db
def test_reject_service_deletes_photos_and_prices(admin_client, pending_service, monkeypatch):
    from services.models import ServicePhoto, ServicePrice
    ServicePhoto.objects.create(
        service=pending_service, telegram_file_id="file1", order_index=0
    )
    ServicePrice.objects.create(
        service=pending_service, price_type=ServicePrice.PriceType.HALF_DAY, amount=500
    )
    monkeypatch.setattr(
        "adminpanel.views.queue_service_rejection_with_reason",
        lambda provider_id, reason: None,
    )
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": "Valid rejection reason here."},
        format="json",
    )
    assert response.status_code == 200
    assert ServicePhoto.objects.filter(service=pending_service).count() == 0
    assert ServicePrice.objects.filter(service=pending_service).count() == 0


@pytest.mark.django_db
def test_reject_service_deletes_bot_session(admin_client, pending_service, monkeypatch):
    from bot.models import BotRegistrationSession
    BotRegistrationSession.objects.create(
        telegram_user_id=pending_service.provider.telegram_id,
        chat_id=999,
        state=BotRegistrationSession.State.SUBMIT,
    )
    monkeypatch.setattr(
        "adminpanel.views.queue_service_rejection_with_reason",
        lambda provider_id, reason: None,
    )
    response = admin_client.post(
        "/api/admin/service/reject/",
        {"service_id": pending_service.id, "rejection_reason": "Valid rejection reason here."},
        format="json",
    )
    assert response.status_code == 200
    assert BotRegistrationSession.objects.filter(
        telegram_user_id=pending_service.provider.telegram_id
    ).exists() is False


@pytest.mark.django_db
def test_build_register_again_keyboard():
    from telegram import InlineKeyboardMarkup
    bot = TelegramBotService()
    keyboard = bot.build_register_again_keyboard()
    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "📝 Register Again"
    assert button.callback_data == "registration:create_service"


@pytest.mark.django_db
def test_send_service_rejection_with_reason_safely_sends_message(monkeypatch):
    from bot.service_notifications import send_service_rejection_with_reason_safely
    sent_args = {}
    class FakeKeyboard:
        pass
    class FakeBot:
        def send_text(self, chat_id, text, reply_markup=None):
            sent_args["chat_id"] = chat_id
            sent_args["text"] = text
            sent_args["reply_markup"] = reply_markup
            return True
        def build_register_again_keyboard(self):
            return FakeKeyboard()
    monkeypatch.setattr(
        "bot.service_notifications.TelegramBotService",
        lambda: FakeBot(),
    )
    send_service_rejection_with_reason_safely(99001, "Test rejection reason")
    assert sent_args["chat_id"] == 99001
    assert "❌" in sent_args["text"]
    assert "Test rejection reason" in sent_args["text"]
    assert "start the registration process again" in sent_args["text"]
    assert isinstance(sent_args["reply_markup"], FakeKeyboard)


@pytest.mark.django_db
def test_send_service_rejection_with_reason_safely_error_handled(monkeypatch):
    from bot.service_notifications import send_service_rejection_with_reason_safely
    class FailingBot:
        def send_text(self, chat_id, text, reply_markup=None):
            raise RuntimeError("Telegram API unavailable")
        def build_register_again_keyboard(self):
            return None
    monkeypatch.setattr(
        "bot.service_notifications.TelegramBotService",
        lambda: FailingBot(),
    )
    # Should not raise — exception is caught internally
    send_service_rejection_with_reason_safely(99001, "Reason")


@pytest.mark.django_db
def test_queue_service_rejection_with_reason_submits(monkeypatch):
    from bot.service_notifications import queue_service_rejection_with_reason
    submitted = []
    monkeypatch.setattr(
        "bot.service_notifications._notification_executor.submit",
        lambda fn, *args: submitted.append((fn, args)),
    )
    queue_service_rejection_with_reason(99001, "A valid reason")
    assert len(submitted) == 1
    fn, args = submitted[0]
    assert args[0] == 99001
    assert args[1] == "A valid reason"


@pytest.mark.django_db
def test_approve_service_no_service_id(admin_client):
    response = admin_client.post(
        "/api/admin/service/approve/",
        {},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_approve_service_non_existent(admin_client):
    response = admin_client.post(
        "/api/admin/service/approve/",
        {"service_id": 99999},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_approve_service_already_approved(admin_client, pending_service):
    pending_service.approval_status = ServiceProfile.ApprovalStatus.APPROVED
    pending_service.save()
    response = admin_client.post(
        "/api/admin/service/approve/",
        {"service_id": pending_service.id},
        format="json",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_registration_reset_button_callback():
    from bot.handler_modules.registration import handle_callback
    from bot.models import BotRegistrationSession
    from bot.handler_modules.utils import TelegramUpdateContext
    
    session = BotRegistrationSession.objects.create(
        telegram_user_id=12345,
        chat_id=12345,
        state=BotRegistrationSession.State.CATEGORY,
    )
    
    class FakeBotService:
        def __init__(self):
            self.sent_messages = []
        def build_role_keyboard(self):
            return "role_keyboard"
        def send_text(self, chat_id, text, reply_markup=None):
            self.sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return True
        def answer_callback(self, callback_query_id, text=None):
            pass
            
    bot = FakeBotService()
    context = TelegramUpdateContext(
        update_id=1,
        telegram_user_id=12345,
        chat_id=12345,
        message=None,
        callback_query={"id": "cb1"},
        username="test_username",
        first_name="Test",
    )
    
    # Trigger callback
    result = handle_callback(bot, context, "registration:reset")
    
    assert result.handled is True
    session.refresh_from_db()
    assert session.state == BotRegistrationSession.State.SELECT_ROLE
    assert len(bot.sent_messages) == 1
    assert "reset" in bot.sent_messages[0]["text"].lower()
    assert bot.sent_messages[0]["reply_markup"] == "role_keyboard"


@pytest.mark.django_db
def test_admin_can_toggle_provider_verified(admin_client, provider):
    assert provider.is_verified is False

    response = admin_client.post(f"/api/admin/provider/{provider.id}/toggle-verified/")
    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["is_verified"] is True

    provider.refresh_from_db()
    assert provider.is_verified is True

    # Toggle back
    response = admin_client.post(f"/api/admin/provider/{provider.id}/toggle-verified/")
    assert response.status_code == 200
    assert response.data["is_verified"] is False

    provider.refresh_from_db()
    assert provider.is_verified is False


@pytest.mark.django_db
def test_admin_can_toggle_provider_tested(admin_client, provider):
    assert provider.admin_tested_badge is False

    response = admin_client.post(f"/api/admin/provider/{provider.id}/toggle-tested/")
    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["admin_tested_badge"] is True

    provider.refresh_from_db()
    assert provider.admin_tested_badge is True


@pytest.mark.django_db
def test_admin_can_toggle_service_admin_visibility(admin_client, pending_service):
    assert pending_service.admin_forced_hidden is False

    response = admin_client.post(
        f"/api/admin/service/{pending_service.id}/toggle-admin-visibility/"
    )
    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["admin_forced_hidden"] is True

    pending_service.refresh_from_db()
    assert pending_service.admin_forced_hidden is True


@pytest.mark.django_db
def test_toggle_verified_non_admin(normal_client, provider):
    response = normal_client.post(f"/api/admin/provider/{provider.id}/toggle-verified/")
    assert response.status_code == 403
    assert response.data["success"] is False


@pytest.mark.django_db
def test_toggle_verified_provider_not_found(admin_client):
    response = admin_client.post("/api/admin/provider/99999/toggle-verified/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_send_registration_reminder_success(admin_client, monkeypatch):
    from bot.models import BotRegistrationSession
    user = TelegramUser.objects.create(
        telegram_id=88001,
        role=TelegramUser.Role.CUSTOMER,
        first_name="RemindMe",
    )
    BotRegistrationSession.objects.create(
        telegram_user_id=user.telegram_id,
        chat_id=user.telegram_id,
        state=BotRegistrationSession.State.CATEGORY,
    )
    sent_calls = []
    monkeypatch.setattr(
        "adminpanel.views._send_registration_reminder",
        lambda tid: sent_calls.append(tid) or True,
    )

    response = admin_client.post(
        "/api/admin/send-registration-reminder/",
        {"telegram_user_id": user.id},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["success"] is True
    assert sent_calls == [user.telegram_id]


@pytest.mark.django_db
def test_send_registration_reminder_no_session(admin_client):
    user = TelegramUser.objects.create(
        telegram_id=88002,
        role=TelegramUser.Role.CUSTOMER,
    )
    response = admin_client.post(
        "/api/admin/send-registration-reminder/",
        {"telegram_user_id": user.id},
        format="json",
    )
    assert response.status_code == 404
    assert response.data["success"] is False
    assert response.data["error"] == "User not found or no active session."


@pytest.mark.django_db
def test_send_registration_reminder_user_not_found(admin_client):
    response = admin_client.post(
        "/api/admin/send-registration-reminder/",
        {"telegram_user_id": 99999},
        format="json",
    )
    assert response.status_code == 404
    assert response.data["success"] is False
    assert response.data["error"] == "User not found or no active session."


@pytest.mark.django_db
def test_send_registration_reminder_missing_param(admin_client):
    response = admin_client.post(
        "/api/admin/send-registration-reminder/",
        {},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_send_registration_reminder_non_admin(normal_client):
    response = normal_client.post(
        "/api/admin/send-registration-reminder/",
        {"telegram_user_id": 88001},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_send_mass_reminders_success(admin_client, monkeypatch):
    from bot.models import BotRegistrationSession
    from django.utils import timezone
    from datetime import timedelta

    # Create a session exactly 2.5 days old (within the 2-3 day window)
    old = timezone.now() - timedelta(days=2, hours=12)
    session = BotRegistrationSession.objects.create(
        telegram_user_id=88003,
        chat_id=88003,
        state=BotRegistrationSession.State.TITLE,
    )
    BotRegistrationSession.objects.filter(id=session.id).update(updated_at=old)

    sent_ids = []
    monkeypatch.setattr(
        "adminpanel.views._send_registration_reminder",
        lambda tid: sent_ids.append(tid) or True,
    )

    response = admin_client.post("/api/admin/send-mass-reminders/")
    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["sent_count"] == 1
    assert response.data["failed_count"] == 0
    assert 88003 in sent_ids


@pytest.mark.django_db
def test_send_mass_reminders_non_admin(normal_client):
    response = normal_client.post("/api/admin/send-mass-reminders/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_toggle_service_visibility_not_found(admin_client):
    response = admin_client.post("/api/admin/service/99999/toggle-admin-visibility/")
    assert response.status_code == 404
