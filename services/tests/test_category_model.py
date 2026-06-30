import pytest
from django.core.exceptions import ValidationError

from services.models import ServiceCategory


@pytest.mark.django_db
def test_service_category_can_be_created():
    category = ServiceCategory.objects.create(name="Electrician")

    assert category.name == "Electrician"
    assert category.active is True
    assert str(category) == "Electrician"


@pytest.mark.django_db
def test_service_category_name_must_be_unique():
    ServiceCategory.objects.create(name="Cleaner")

    with pytest.raises(ValidationError):
        ServiceCategory.objects.create(name="Cleaner")


@pytest.mark.django_db
def test_service_category_active_flag_can_be_false():
    category = ServiceCategory.objects.create(
        name="Tutor",
        active=False,
    )

    assert category.active is False


@pytest.mark.django_db
def test_service_category_name_is_normalized():
    category = ServiceCategory.objects.create(name="   Home    Cleaner   ")

    assert category.name == "Home Cleaner"


@pytest.mark.django_db
def test_service_category_name_is_required():
    category = ServiceCategory(name="   ")

    with pytest.raises(ValidationError):
        category.full_clean()
