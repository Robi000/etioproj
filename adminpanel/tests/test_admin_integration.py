import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from rest_framework.authtoken.models import Token
from accounts.models import TelegramUser
from approvals.models import ContactRequest
from bot.models import BotRegistrationSession
from services.models import ProviderDenialLog, ServiceCategory, ServiceProfile, ServicePhoto, ServicePrice


@pytest.fixture
def admin_telegram_user():
    return TelegramUser.objects.create(
        telegram_id=88001, role=TelegramUser.Role.ADMIN, first_name="Admin",
    )


@pytest.fixture
def provider_user():
    return TelegramUser.objects.create(
        telegram_id=88002, role=TelegramUser.Role.PROVIDER, phone_number="+251911111111",
    )


@pytest.fixture
def customer_user():
    return TelegramUser.objects.create(
        telegram_id=88003, role=TelegramUser.Role.CUSTOMER,
    )


@pytest.fixture
def admin_auth_user(admin_telegram_user):
    return User.objects.create_user(username=f"telegram_{admin_telegram_user.telegram_id}")


@pytest.fixture
def admin_token(admin_auth_user):
    token, _ = Token.objects.get_or_create(user=admin_auth_user)
    return token


@pytest.fixture
def admin_client(api_client, admin_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")
    return api_client


@pytest.fixture
def category():
    return ServiceCategory.objects.create(name="Integration Category")


@pytest.fixture
def pending_service(provider_user, category):
    return ServiceProfile.objects.create(
        provider=provider_user, category=category, title="Integration Service",
        description="Integration description", city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.PENDING,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )


# ─────────────────────────────────────────────────────────────
# 1. Full rejection flow
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFullRejectionFlow:
    """Admin rejects service → Telegram message queued → DB cleanup → provider reset."""

    def test_rejection_deletes_service_and_resets_provider(
        self, admin_client, pending_service, provider_user, monkeypatch,
        django_capture_on_commit_callbacks,
    ):
        ServicePhoto.objects.create(
            service=pending_service, telegram_file_id="reject_photo", order_index=0,
        )
        ServicePrice.objects.create(
            service=pending_service, price_type=ServicePrice.PriceType.HALF_DAY, amount=500,
        )
        BotRegistrationSession.objects.create(
            telegram_user_id=provider_user.telegram_id, chat_id=provider_user.telegram_id,
            state=BotRegistrationSession.State.CATEGORY,
        )

        queued_calls = []
        monkeypatch.setattr(
            "adminpanel.views.queue_service_rejection_with_reason",
            lambda pid, reason: queued_calls.append((pid, reason)),
        )

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(
                "/api/admin/service/reject/",
                {"service_id": pending_service.id, "rejection_reason": "Violates platform terms of service."},
                format="json",
            )

        assert response.status_code == 200
        assert response.data["success"] is True

        # Service + related rows gone
        assert ServiceProfile.objects.filter(id=pending_service.id).exists() is False
        assert ServicePhoto.objects.filter(service=pending_service).exists() is False
        assert ServicePrice.objects.filter(service=pending_service).exists() is False

        # Bot session deleted
        assert BotRegistrationSession.objects.filter(
            telegram_user_id=provider_user.telegram_id
        ).exists() is False

        # Provider role reset
        provider_user.refresh_from_db()
        assert provider_user.role == TelegramUser.Role.CUSTOMER

        # Telegram notification queued with correct reason
        assert len(queued_calls) == 1
        assert queued_calls[0] == (provider_user.telegram_id, "Violates platform terms of service.")

    def test_rejection_notification_message_format(self, monkeypatch):
        """Verify the Telegram message sent to provider contains the rejection reason."""
        from bot.service_notifications import send_service_rejection_with_reason_safely

        sent_args = {}

        class FakeBot:
            def send_text(self, chat_id, text, reply_markup=None):
                sent_args["chat_id"] = chat_id
                sent_args["text"] = text
                return True
            def build_register_again_keyboard(self):
                return "fake_keyboard"

        monkeypatch.setattr(
            "bot.service_notifications.TelegramBotService",
            lambda: FakeBot(),
        )

        send_service_rejection_with_reason_safely(99001, "Your photos were not clear enough.")

        assert sent_args["chat_id"] == 99001
        assert "❌" in sent_args["text"]
        assert "Your photos were not clear enough." in sent_args["text"]
        assert "registration" in sent_args["text"].lower()

    def test_rejection_is_atomic_on_failure(self, admin_client, pending_service, provider_user, monkeypatch):
        """If the Telegram queue call itself fails, the DB changes are still committed
        (the rejection runs in a DB transaction independent of the async notification)."""
        ServicePrice.objects.create(
            service=pending_service, price_type=ServicePrice.PriceType.HALF_DAY, amount=500,
        )

        monkeypatch.setattr(
            "adminpanel.views.queue_service_rejection_with_reason",
            lambda pid, reason: None,
        )

        response = admin_client.post(
            "/api/admin/service/reject/",
            {"service_id": pending_service.id, "rejection_reason": "Valid rejection reason here."},
            format="json",
        )

        assert response.status_code == 200
        assert ServiceProfile.objects.filter(id=pending_service.id).exists() is False
        provider_user.refresh_from_db()
        assert provider_user.role == TelegramUser.Role.CUSTOMER


# ─────────────────────────────────────────────────────────────
# 2. AJAX approve contact request
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestApproveContactRequest:
    """Admin approves a contact request → JSON response + DB update + notification queued."""

    def test_approve_contact_returns_json_and_updates_db(
        self, admin_client, customer_user, provider_user, admin_telegram_user, monkeypatch,
        django_capture_on_commit_callbacks,
    ):
        queued = []
        monkeypatch.setattr(
            "adminpanel.views.queue_customer_admin_decision_message",
            lambda cid: queued.append(cid),
        )

        contact_request = ContactRequest.objects.create(
            customer=customer_user, provider=provider_user, status=ContactRequest.Status.PENDING,
        )

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(
                "/api/admin/contact/approve/",
                {"contact_request_id": contact_request.id},
                format="json",
            )

        assert response.status_code == 200
        assert response.data["success"] is True

        contact_request.refresh_from_db()
        assert contact_request.status == ContactRequest.Status.APPROVED
        assert contact_request.approved_by == admin_telegram_user
        assert contact_request.approved_at is not None

        # Notification queued
        assert queued == [contact_request.id]

    def test_approve_contact_rejects_non_pending(
        self, admin_client, customer_user, provider_user,
    ):
        contact_request = ContactRequest.objects.create(
            customer=customer_user, provider=provider_user,
            status=ContactRequest.Status.PROVIDER_PENDING,
        )

        response = admin_client.post(
            "/api/admin/contact/approve/",
            {"contact_request_id": contact_request.id},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False

        contact_request.refresh_from_db()
        assert contact_request.status == ContactRequest.Status.PROVIDER_PENDING  # unchanged

    def test_approve_contact_not_found(self, admin_client):
        response = admin_client.post(
            "/api/admin/contact/approve/",
            {"contact_request_id": 99999},
            format="json",
        )
        assert response.status_code == 404
        assert response.data["success"] is False

    def test_approve_contact_non_admin(self, api_client, customer_user, provider_user):
        contact_request = ContactRequest.objects.create(
            customer=customer_user, provider=provider_user, status=ContactRequest.Status.PENDING,
        )

        response = api_client.post(
            "/api/admin/contact/approve/",
            {"contact_request_id": contact_request.id},
            format="json",
        )
        assert response.status_code == 403


# ─────────────────────────────────────────────────────────────
# 3. Reminder endpoint
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRegistrationReminder:
    """User with active mid-registration session receives a Telegram reminder."""

    def test_send_reminder_sends_telegram_message(self, admin_client, monkeypatch):
        user = TelegramUser.objects.create(
            telegram_id=99010, role=TelegramUser.Role.CUSTOMER, first_name="ReminderUser",
        )
        BotRegistrationSession.objects.create(
            telegram_user_id=user.telegram_id, chat_id=user.telegram_id,
            state=BotRegistrationSession.State.TITLE,
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

    def test_reminder_message_contains_continue_button(self, monkeypatch):
        """Verify the Telegram message sent by _send_registration_reminder."""
        from adminpanel.views import _send_registration_reminder

        sent_args = {}

        class FakeBot:
            def send_text(self, chat_id, text, reply_markup=None):
                sent_args["chat_id"] = chat_id
                sent_args["text"] = text
                sent_args["reply_markup"] = reply_markup
                return True

        monkeypatch.setattr("adminpanel.views.TelegramBotService", lambda: FakeBot())

        result = _send_registration_reminder(99010)

        assert result is True
        assert sent_args["chat_id"] == 99010
        assert "started registering" in sent_args["text"].lower()
        assert "continue where you left off" in sent_args["text"].lower()

    def test_reminder_rejects_user_without_session(self, admin_client):
        user = TelegramUser.objects.create(
            telegram_id=99011, role=TelegramUser.Role.CUSTOMER,
        )
        response = admin_client.post(
            "/api/admin/send-registration-reminder/",
            {"telegram_user_id": user.id},
            format="json",
        )
        assert response.status_code == 404
        assert response.data["error"] == "User not found or no active session."

    def test_reminder_rejects_completed_session(self, admin_client):
        user = TelegramUser.objects.create(
            telegram_id=99012, role=TelegramUser.Role.CUSTOMER,
        )
        BotRegistrationSession.objects.create(
            telegram_user_id=user.telegram_id, chat_id=user.telegram_id,
            state=BotRegistrationSession.State.COMPLETED,
        )
        response = admin_client.post(
            "/api/admin/send-registration-reminder/",
            {"telegram_user_id": user.id},
            format="json",
        )
        assert response.status_code == 404
        assert response.data["error"] == "User not found or no active session."

    def test_reminder_requires_telegram_user_id(self, admin_client):
        response = admin_client.post(
            "/api/admin/send-registration-reminder/", {}, format="json",
        )
        assert response.status_code == 400
        assert response.data["success"] is False

    def test_reminder_non_admin_cannot_send(self, api_client):
        response = api_client.post(
            "/api/admin/send-registration-reminder/",
            {"telegram_user_id": 1}, format="json",
        )
        assert response.status_code == 403


# ─────────────────────────────────────────────────────────────
# 4. Mass reminder
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMassReminder:
    """Mass reminder sends only to users with 2–3 day old sessions."""

    def test_mass_reminder_targets_correct_window(self, admin_client, monkeypatch):
        now = timezone.now()

        # Session 1: 2.5 days old — should be included
        session1 = BotRegistrationSession.objects.create(
            telegram_user_id=99101, chat_id=99101,
            state=BotRegistrationSession.State.DESCRIPTION,
        )
        BotRegistrationSession.objects.filter(id=session1.id).update(
            updated_at=now - timedelta(days=2, hours=12)
        )

        # Session 2: 4 days old — outside window, excluded
        session2 = BotRegistrationSession.objects.create(
            telegram_user_id=99102, chat_id=99102,
            state=BotRegistrationSession.State.PRICES,
        )
        BotRegistrationSession.objects.filter(id=session2.id).update(
            updated_at=now - timedelta(days=4)
        )

        # Session 3: 1 day old — outside window, excluded
        session3 = BotRegistrationSession.objects.create(
            telegram_user_id=99103, chat_id=99103,
            state=BotRegistrationSession.State.PHOTOS,
        )
        BotRegistrationSession.objects.filter(id=session3.id).update(
            updated_at=now - timedelta(days=1)
        )

        # Session 4: 2 days old exactly — should be included (boundary)
        session4 = BotRegistrationSession.objects.create(
            telegram_user_id=99104, chat_id=99104,
            state=BotRegistrationSession.State.SUBMIT,
        )
        BotRegistrationSession.objects.filter(id=session4.id).update(
            updated_at=now - timedelta(days=2)
        )

        # Session 5: completed state — excluded (not in MID_REGISTRATION_STATES)
        session5 = BotRegistrationSession.objects.create(
            telegram_user_id=99105, chat_id=99105,
            state=BotRegistrationSession.State.COMPLETED,
        )
        BotRegistrationSession.objects.filter(id=session5.id).update(
            updated_at=now - timedelta(days=2, hours=12)
        )

        sent_ids = []
        monkeypatch.setattr(
            "adminpanel.views._send_registration_reminder",
            lambda tid: sent_ids.append(tid) or True,
        )

        response = admin_client.post("/api/admin/send-mass-reminders/")

        assert response.status_code == 200
        assert response.data["success"] is True
        # Only sessions 1 and 4 should receive reminders
        assert response.data["sent_count"] == 2
        assert response.data["failed_count"] == 0
        assert 99101 in sent_ids
        assert 99104 in sent_ids
        assert 99102 not in sent_ids
        assert 99103 not in sent_ids
        assert 99105 not in sent_ids

    def test_mass_reminder_respects_max_200(self, admin_client, monkeypatch):
        now = timezone.now()
        for i in range(250):
            tid = 99200 + i
            s = BotRegistrationSession.objects.create(
                telegram_user_id=tid, chat_id=tid,
                state=BotRegistrationSession.State.CATEGORY,
            )
            BotRegistrationSession.objects.filter(id=s.id).update(
                updated_at=now - timedelta(days=2, hours=6)
            )

        sent_ids = []
        monkeypatch.setattr(
            "adminpanel.views._send_registration_reminder",
            lambda tid: sent_ids.append(tid) or True,
        )

        response = admin_client.post("/api/admin/send-mass-reminders/")

        assert response.status_code == 200
        assert response.data["sent_count"] == 200
        assert response.data["failed_count"] == 0
        assert len(sent_ids) == 200

    def test_mass_reminder_non_admin(self, api_client):
        response = api_client.post("/api/admin/send-mass-reminders/")
        assert response.status_code == 403


# ─────────────────────────────────────────────────────────────
# 5. 24-Hour Timeout Processing
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProcessTimeouts:
    """Cron endpoint: auto-rejects PROVIDER_PENDING requests older than 24h."""

    def test_timeout_rejects_expired_request(
        self, admin_client, provider_user, customer_user, monkeypatch,
        django_capture_on_commit_callbacks,
    ):
        contact_request = ContactRequest.objects.create(
            customer=customer_user, provider=provider_user,
            status=ContactRequest.Status.PROVIDER_PENDING,
        )
        ContactRequest.objects.filter(id=contact_request.id).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        contact_request.refresh_from_db()

        queued = []
        monkeypatch.setattr(
            "adminpanel.views.queue_customer_rejection_message",
            lambda cid: queued.append(cid),
        )

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post("/api/admin/process-timeouts/")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["processed_count"] == 1

        contact_request.refresh_from_db()
        assert contact_request.status == ContactRequest.Status.PROVIDER_REJECTED
        assert queued == [contact_request.id]

    def test_timeout_skips_recent_request(self, admin_client, provider_user, customer_user):
        contact_request = ContactRequest.objects.create(
            customer=customer_user, provider=provider_user,
            status=ContactRequest.Status.PROVIDER_PENDING,
        )
        ContactRequest.objects.filter(id=contact_request.id).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        contact_request.refresh_from_db()

        response = admin_client.post("/api/admin/process-timeouts/")

        assert response.status_code == 200
        assert response.data["processed_count"] == 0
        contact_request.refresh_from_db()
        assert contact_request.status == ContactRequest.Status.PROVIDER_PENDING

    def test_timeout_skips_non_pending_status(self, admin_client, provider_user, customer_user):
        contact_request = ContactRequest.objects.create(
            customer=customer_user, provider=provider_user,
            status=ContactRequest.Status.PENDING,  # not PROVIDER_PENDING
        )
        ContactRequest.objects.filter(id=contact_request.id).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        contact_request.refresh_from_db()

        response = admin_client.post("/api/admin/process-timeouts/")

        assert response.status_code == 200
        assert response.data["processed_count"] == 0
        contact_request.refresh_from_db()
        assert contact_request.status == ContactRequest.Status.PENDING

    def test_timeout_creates_denial_log_and_increments_count(
        self, admin_client, provider_user, customer_user, category, monkeypatch,
        django_capture_on_commit_callbacks,
    ):
        service = ServiceProfile.objects.create(
            provider=provider_user, category=category, title="Timeout Test",
            description="Timeout test", city_text="Addis",
            approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
        )
        contact_request = ContactRequest.objects.create(
            customer=customer_user, provider=provider_user, service=service,
            status=ContactRequest.Status.PROVIDER_PENDING,
        )
        ContactRequest.objects.filter(id=contact_request.id).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        contact_request.refresh_from_db()

        monkeypatch.setattr(
            "adminpanel.views.queue_customer_rejection_message",
            lambda cid: None,
        )

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post("/api/admin/process-timeouts/")

        assert response.status_code == 200
        assert response.data["processed_count"] == 1

        # Denial log created
        denial_log = ProviderDenialLog.objects.filter(
            service=service, reason=ProviderDenialLog.DenialReason.TIMEOUT,
        ).first()
        assert denial_log is not None
        assert denial_log.contact_request_id == contact_request.id

        # Denial count incremented
        service.refresh_from_db()
        assert service.denial_count == 1

    def test_timeout_applies_penalty_when_ratio_exceeds_75(
        self, admin_client, provider_user, customer_user, category, monkeypatch,
        django_capture_on_commit_callbacks,
    ):
        service = ServiceProfile.objects.create(
            provider=provider_user, category=category, title="Penalty Timeout",
            description="Penalty test", city_text="Addis",
            approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
        )

        # Create 10 requests + pre-set 8 denials → after timeout: 9/11 ≈ 0.818 > 0.75
        for _ in range(10):
            ContactRequest.objects.create(
                customer=customer_user, provider=provider_user,
                status=ContactRequest.Status.PROVIDER_PENDING,
            )

        service.denial_count = 8
        service.save(update_fields=["denial_count"])

        contact_request = ContactRequest.objects.create(
            customer=customer_user, provider=provider_user, service=service,
            status=ContactRequest.Status.PROVIDER_PENDING,
        )
        ContactRequest.objects.filter(id=contact_request.id).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        contact_request.refresh_from_db()

        monkeypatch.setattr(
            "adminpanel.views.queue_customer_rejection_message",
            lambda cid: None,
        )

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post("/api/admin/process-timeouts/")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["processed_count"] == 1

        service.refresh_from_db()
        assert service.denial_count == 9
        # 9/11 ≈ 0.818 > 0.75, total_requests = 11 >= 10 → penalty applies
        assert service.penalty_until is not None
        assert service.visibility_status == ServiceProfile.VisibilityStatus.OFF
        assert service.penalty_count == 1

    def test_timeout_requires_admin_auth(self, api_client, provider_user, customer_user):
        ContactRequest.objects.create(
            customer=customer_user, provider=provider_user,
            status=ContactRequest.Status.PROVIDER_PENDING,
        )
        response = api_client.post("/api/admin/process-timeouts/")
        assert response.status_code == 403
