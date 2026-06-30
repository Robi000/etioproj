import pytest
from django.core.exceptions import ValidationError

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServiceProfile


@pytest.fixture
def provider_user():
    return TelegramUser.objects.create(
        telegram_id=9001,
        telegram_username="provider_user",
        first_name="Provider",
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def admin_user():
    return TelegramUser.objects.create(
        telegram_id=9002,
        telegram_username="admin_user",
        first_name="Admin",
        role=TelegramUser.Role.ADMIN,
    )


@pytest.fixture
def category():
    return ServiceCategory.objects.create(name="Electrician")


@pytest.mark.django_db
def test_service_profile_can_be_created_with_city_text(provider_user, category):
    profile = ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Professional Electrician",
        description="Electrical repair and installation service.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )

    assert profile.provider == provider_user
    assert profile.category == category
    assert profile.title == "Professional Electrician"
    assert profile.city_text == "Addis Ababa"
    assert profile.visibility_status == ServiceProfile.VisibilityStatus.ON
    assert profile.approval_status == ServiceProfile.ApprovalStatus.PENDING


@pytest.mark.django_db
def test_one_provider_cannot_create_two_service_profiles(provider_user, category):
    ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="First Service",
        description="First service description.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )

    with pytest.raises(ValidationError):
        ServiceProfile.objects.create(
            provider=provider_user,
            category=category,
            title="Second Service",
            description="Second service description.",
            city_text="Adama",
            location_source=ServiceProfile.LocationSource.CITY_TEXT,
        )


@pytest.mark.django_db
def test_service_profile_can_be_created_with_gps(provider_user, category):
    profile = ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="GPS Service",
        description="Service with GPS location.",
        latitude="9.030000",
        longitude="38.740000",
        location_source=ServiceProfile.LocationSource.GPS,
    )

    assert str(profile.latitude) == "9.030000"
    assert str(profile.longitude) == "38.740000"
    assert profile.location_source == ServiceProfile.LocationSource.GPS


@pytest.mark.django_db
def test_city_text_location_requires_city(provider_user, category):
    profile = ServiceProfile(
        provider=provider_user,
        category=category,
        title="Invalid Location Service",
        description="Missing city text.",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )

    with pytest.raises(ValidationError):
        profile.full_clean()


@pytest.mark.django_db
def test_invalid_latitude_is_rejected(provider_user, category):
    profile = ServiceProfile(
        provider=provider_user,
        category=category,
        title="Invalid Latitude Service",
        description="Invalid latitude.",
        latitude="120.000000",
        longitude="38.740000",
        location_source=ServiceProfile.LocationSource.GPS,
    )

    with pytest.raises(ValidationError):
        profile.full_clean()


@pytest.mark.django_db
def test_approved_visible_non_banned_profile_is_discoverable(provider_user, admin_user, category):
    profile = ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Approved Service",
        description="Approved service description.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        approved_by=admin_user,
    )

    assert profile.is_discoverable_candidate is True


@pytest.mark.django_db
def test_visibility_off_profile_is_not_discoverable(provider_user, admin_user, category):
    profile = ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Hidden Service",
        description="Hidden service description.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        visibility_status=ServiceProfile.VisibilityStatus.OFF,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        approved_by=admin_user,
    )

    assert profile.is_discoverable_candidate is False


@pytest.mark.django_db
def test_service_profile_moderation_discovery(provider_user, admin_user, category):
    from datetime import timedelta
    from django.utils import timezone
    
    profile = ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Moderated Service",
        description="Test service.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        approved_by=admin_user,
    )
    
    assert profile.is_discoverable_candidate is True

    # Forced hidden
    profile.admin_forced_hidden = True
    profile.save()
    assert profile.is_discoverable_candidate is False

    profile.admin_forced_hidden = False
    profile.save()
    assert profile.is_discoverable_candidate is True

    # Future penalty
    profile.penalty_until = timezone.now() + timedelta(hours=1)
    profile.save()
    assert profile.is_discoverable_candidate is False

    # Past penalty
    profile.penalty_until = timezone.now() - timedelta(hours=1)
    profile.save()
    assert profile.is_discoverable_candidate is True


@pytest.mark.django_db
def test_city_location_bounds_matching():
    from services.models import CityLocation

    # Addis Ababa boundary check: 38.6231 to 38.93948 (X/lon), 8.850684 to 9.1236 (Y/lat)
    assert CityLocation.get_city_for_coordinates(38.740000, 9.030000) == "Addis Ababa"
    
    # Adama boundary check: 39.2079 to 39.32624 (X/lon), 8.461662 to 8.597673 (Y/lat)
    assert CityLocation.get_city_for_coordinates(39.270000, 8.540000) == "Adama"

    # Hawassa boundary check: 38.44405 to 38.53664 (X/lon), 7.003403 to 7.113437 (Y/lat)
    assert CityLocation.get_city_for_coordinates(38.480000, 7.050000) == "Hawassa"

    # Mekele boundary check: 39.42369 to 39.52371 (X/lon), 13.45773 to 13.58272 (Y/lat)
    assert CityLocation.get_city_for_coordinates(39.470000, 13.520000) == "Mekele"

    # Outside all cities
    assert CityLocation.get_city_for_coordinates(35.000000, 5.000000) is None
    assert CityLocation.get_city_for_coordinates(None, None) is None
