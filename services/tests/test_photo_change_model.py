import pytest
from django.db import IntegrityError

from accounts.models import TelegramUser
from services.models import PhotoChangeRequest, ServiceCategory, ServiceProfile


@pytest.fixture
def service():
    provider = TelegramUser.objects.create(
        telegram_id=91001,
        role=TelegramUser.Role.PROVIDER,
        first_name="Provider",
        phone_number="+251911111111",
    )
    category = ServiceCategory.objects.create(name="PCR Category")
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title="PCR Service",
        description="Test",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
    )


@pytest.mark.django_db
class TestPhotoChangeRequestModel:
    def test_fields(self, service):
        change = PhotoChangeRequest.objects.create(
            service=service,
            new_file_id="abc123",
            order_index=2,
        )
        assert change.service_id == service.id
        assert change.new_file_id == "abc123"
        assert change.order_index == 2
        assert change.status == PhotoChangeRequest.Status.PENDING
        assert change.created_at is not None
        assert change.approved_at is None

    def test_status_choices(self, service):
        change = PhotoChangeRequest.objects.create(
            service=service, new_file_id="f1", order_index=1,
        )
        for status in [PhotoChangeRequest.Status.PENDING,
                       PhotoChangeRequest.Status.APPROVED,
                       PhotoChangeRequest.Status.REJECTED]:
            change.status = status
            change.save()
            change.refresh_from_db()
            assert change.status == status

    def test_ordering(self, service):
        c1 = PhotoChangeRequest.objects.create(
            service=service, new_file_id="f1", order_index=1,
        )
        c2 = PhotoChangeRequest.objects.create(
            service=service, new_file_id="f2", order_index=2,
        )
        qs = PhotoChangeRequest.objects.all()
        assert list(qs) == [c2, c1]

    def test_cascade_delete(self, service):
        change = PhotoChangeRequest.objects.create(
            service=service, new_file_id="f1", order_index=1,
        )
        change_id = change.id
        service.delete()
        assert PhotoChangeRequest.objects.filter(id=change_id).count() == 0
