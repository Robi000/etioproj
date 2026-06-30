from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import PhotoChangeRequest, ServiceCategory, ServicePhoto, ServiceProfile


@pytest.fixture
def admin_user():
    u = User.objects.create_superuser(
        username="admin",
        password="adminpass",
        email="admin@example.com",
    )
    token, _ = Token.objects.get_or_create(user=u)
    return u, token


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=90001,
        role=TelegramUser.Role.PROVIDER,
        first_name="TestProvider",
        phone_number="+251911111111",
    )


@pytest.fixture
def category():
    return ServiceCategory.objects.create(name="Photo Test Cat")


@pytest.fixture
def service(provider, category):
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="Photo Change Service",
        description="Test",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )


@pytest.fixture
def pending_change(service):
    return PhotoChangeRequest.objects.create(
        service=service,
        new_file_id="new_file_abc123",
        order_index=1,
    )


def make_patch_executor():
    class SyncExecutor:
        def submit(self, fn, *args, **kwargs):
            fut = __import__("concurrent.futures").futures.Future()
            try:
                fut.set_result(fn(*args, **kwargs))
            except Exception as e:
                fut.set_exception(e)
            return fut
        def shutdown(self, wait=True):
            pass
    return patch("adminpanel.views._advertisement_executor", SyncExecutor())


@pytest.mark.django_db
class TestPhotoChangeAPI:
    def test_list_pending(self, api_client, admin_user, pending_change):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.get("/api/admin/photo-changes/pending/")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert len(response.data["photo_changes"]) == 1
        assert response.data["photo_changes"][0]["id"] == pending_change.id
        assert response.data["photo_changes"][0]["status"] == "pending"

    def test_list_pending_requires_auth(self, api_client):
        response = api_client.get("/api/admin/photo-changes/pending/")
        assert response.status_code == 403

    def test_list_pending_non_admin_forbidden(self, api_client):
        user = User.objects.create_user(username="regular_user")
        token, _ = Token.objects.get_or_create(user=user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.get("/api/admin/photo-changes/pending/")
        assert response.status_code == 403

    def test_approve_creates_photo(self, api_client, admin_user, pending_change, service):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        with patch("adminpanel.views.TelegramBotService"):
            response = api_client.post(
                f"/api/admin/photo-change/{pending_change.id}/approve/",
                format="json",
            )

        assert response.status_code == 200
        assert response.data["success"] is True

        pending_change.refresh_from_db()
        assert pending_change.status == PhotoChangeRequest.Status.APPROVED
        assert pending_change.approved_at is not None

        photo = ServicePhoto.objects.filter(service=service, order_index=1).first()
        assert photo is not None
        assert photo.telegram_file_id == "new_file_abc123"

    def test_approve_updates_existing_photo(self, api_client, admin_user, service):
        existing = ServicePhoto.objects.create(
            service=service,
            telegram_file_id="old_file_id",
            order_index=1,
        )
        change = PhotoChangeRequest.objects.create(
            service=service,
            new_file_id="updated_file_id",
            order_index=1,
        )

        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        with patch("adminpanel.views.TelegramBotService"):
            response = api_client.post(
                f"/api/admin/photo-change/{change.id}/approve/",
                format="json",
            )

        assert response.status_code == 200

        existing.refresh_from_db()
        assert existing.telegram_file_id == "updated_file_id"

    def test_approve_not_found(self, api_client, admin_user):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.post(
            "/api/admin/photo-change/99999/approve/",
            format="json",
        )
        assert response.status_code == 404

    def test_reject_updates_status(self, api_client, admin_user, pending_change):
        u, token = admin_user
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        with patch("adminpanel.views.TelegramBotService"):
            response = api_client.post(
                f"/api/admin/photo-change/{pending_change.id}/reject/",
                format="json",
            )

        assert response.status_code == 200
        assert response.data["success"] is True

        pending_change.refresh_from_db()
        assert pending_change.status == PhotoChangeRequest.Status.REJECTED

    def test_approve_requires_auth(self, api_client, pending_change):
        response = api_client.post(
            f"/api/admin/photo-change/{pending_change.id}/approve/",
            format="json",
        )
        assert response.status_code == 403

    def test_reject_requires_auth(self, api_client, pending_change):
        response = api_client.post(
            f"/api/admin/photo-change/{pending_change.id}/reject/",
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestPhotoChangeModel:
    def test_create_request(self, service):
        change = PhotoChangeRequest.objects.create(
            service=service,
            new_file_id="test_file_id",
            order_index=2,
        )
        assert change.status == PhotoChangeRequest.Status.PENDING
        assert change.service == service
        assert change.new_file_id == "test_file_id"
        assert change.order_index == 2
        assert change.created_at is not None
        assert change.approved_at is None

    def test_default_status_pending(self, service):
        change = PhotoChangeRequest.objects.create(
            service=service,
            new_file_id="file",
            order_index=1,
        )
        assert change.status == "pending"

    def test_str_representation(self, service):
        change = PhotoChangeRequest.objects.create(
            service=service,
            new_file_id="file",
            order_index=1,
        )
        expected = f"PhotoChange service={service.id} index=1 status=pending"
        assert str(change) == expected


@pytest.mark.django_db
class TestPhotoChangeBotFlow:
    def test_add_photo_creates_change_request_when_approved(self, service, provider):
        from bot.profile_management import add_photo

        with patch("bot.service_notifications.queue_photo_change_admin_notification"):
            success, message = add_photo(provider.telegram_id, "new_file_id")

        assert success is True
        assert "submitted for admin review" in message

        assert PhotoChangeRequest.objects.count() == 1
        change = PhotoChangeRequest.objects.first()
        assert change.service == service
        assert change.new_file_id == "new_file_id"
        assert change.order_index == 1

    def test_add_photo_direct_when_pending(self, admin_user, category):
        provider = TelegramUser.objects.create(
            telegram_id=90002,
            role=TelegramUser.Role.PROVIDER,
            first_name="PendingProvider",
            phone_number="+251922222222",
        )
        service = ServiceProfile.objects.create(
            provider=provider,
            category=category,
            title="Pending Service",
            description="Test",
            city_text="Addis Ababa",
            location_source=ServiceProfile.LocationSource.CITY_TEXT,
            approval_status=ServiceProfile.ApprovalStatus.PENDING,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
        )

        from bot.profile_management import add_photo

        success, message = add_photo(provider.telegram_id, "direct_file_id")

        assert success is True
        assert "saved" in message

        assert PhotoChangeRequest.objects.count() == 0
        assert ServicePhoto.objects.filter(service=service).count() == 1

    def test_add_photo_no_service(self):
        from bot.profile_management import add_photo

        success, message = add_photo(99999, "file_id")
        assert success is False
        assert "No provider profile" in message
