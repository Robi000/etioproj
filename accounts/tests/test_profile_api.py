import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServiceProfile


@pytest.fixture
def telegram_user():
    return TelegramUser.objects.create(
        telegram_id=33333,
        telegram_username="old_username",
        first_name="Old",
        last_name="Name",
        role=TelegramUser.Role.CUSTOMER,
    )


@pytest.fixture
def auth_user(telegram_user):
    return User.objects.create_user(
        username=f"telegram_{telegram_user.telegram_id}",
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
    )


@pytest.fixture
def token(auth_user):
    token, _ = Token.objects.get_or_create(user=auth_user)
    return token


@pytest.fixture
def authenticated_client(api_client, token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )
    return api_client


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Profile API Category"
    )


@pytest.fixture
def service_profile(telegram_user, category):
    telegram_user.role = TelegramUser.Role.PROVIDER
    telegram_user.save()

    return ServiceProfile.objects.create(
        provider=telegram_user,
        category=category,
        title="Profile API Service",
        description="Profile API Service Description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )


@pytest.mark.django_db
def test_patch_profile_updates_basic_user_fields(authenticated_client):
    response = authenticated_client.patch(
        "/api/profile/",
        {
            "first_name": "New",
            "last_name": "Person",
            "telegram_username": "new_username",
            "phone_number": "+251900000000",
            "role": TelegramUser.Role.BOTH,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["user"]["first_name"] == "New"
    assert response.data["user"]["last_name"] == "Person"
    assert response.data["user"]["telegram_username"] == "new_username"
    assert response.data["user"]["phone_number"] == "+251900000000"
    assert response.data["user"]["role"] == TelegramUser.Role.BOTH


@pytest.mark.django_db
def test_patch_profile_rejects_invalid_role(authenticated_client):
    response = authenticated_client.patch(
        "/api/profile/",
        {
            "role": "invalid_role",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False


@pytest.mark.django_db
def test_patch_location_requires_service_profile(authenticated_client):
    response = authenticated_client.patch(
        "/api/profile/location/",
        {
            "city_text": "Adama",
        },
        format="json",
    )

    assert response.status_code == 404
    assert response.data["success"] is False


@pytest.mark.django_db
def test_patch_location_updates_city_text(authenticated_client, service_profile):
    response = authenticated_client.patch(
        "/api/profile/location/",
        {
            "city_text": "Adama",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["location"]["city_text"] == "Adama"
    assert response.data["location"]["location_source"] == ServiceProfile.LocationSource.CITY_TEXT


@pytest.mark.django_db
def test_patch_location_updates_gps(authenticated_client, service_profile):
    response = authenticated_client.patch(
        "/api/profile/location/",
        {
            "latitude": "9.030000",
            "longitude": "38.740000",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["location"]["latitude"] == "9.030000"
    assert response.data["location"]["longitude"] == "38.740000"
    assert response.data["location"]["location_source"] == ServiceProfile.LocationSource.BOTH


@pytest.mark.django_db
def test_patch_location_rejects_invalid_coordinates(authenticated_client, service_profile):
    response = authenticated_client.patch(
        "/api/profile/location/",
        {
            "latitude": "120.000000",
            "longitude": "38.740000",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False


@pytest.mark.django_db
def test_patch_visibility_requires_service_profile(authenticated_client):
    response = authenticated_client.patch(
        "/api/profile/visibility/",
        {
            "visibility_status": ServiceProfile.VisibilityStatus.OFF,
        },
        format="json",
    )

    assert response.status_code == 404
    assert response.data["success"] is False


@pytest.mark.django_db
def test_patch_visibility_updates_service_profile(authenticated_client, service_profile):
    response = authenticated_client.patch(
        "/api/profile/visibility/",
        {
            "visibility_status": ServiceProfile.VisibilityStatus.OFF,
        },
        format="json",
    )

    service_profile.refresh_from_db()

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["visibility_status"] == ServiceProfile.VisibilityStatus.OFF
    assert service_profile.visibility_status == ServiceProfile.VisibilityStatus.OFF


@pytest.mark.django_db
def test_post_visibility_updates_service_profile(authenticated_client, service_profile):
    response = authenticated_client.post(
        "/api/profile/visibility/",
        {
            "visibility_status": ServiceProfile.VisibilityStatus.OFF,
        },
        format="json",
    )

    service_profile.refresh_from_db()

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["visibility_status"] == ServiceProfile.VisibilityStatus.OFF
    assert service_profile.visibility_status == ServiceProfile.VisibilityStatus.OFF


@pytest.mark.django_db
def test_patch_visibility_rejects_invalid_value(authenticated_client, service_profile):
    response = authenticated_client.patch(
        "/api/profile/visibility/",
        {
            "visibility_status": "invalid",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False
