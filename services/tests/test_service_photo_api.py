import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServicePhoto, ServiceProfile


@pytest.fixture
def provider_user():
    return TelegramUser.objects.create(
        telegram_id=66661,
        telegram_username="photo_provider",
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def other_provider_user():
    return TelegramUser.objects.create(
        telegram_id=66662,
        telegram_username="other_photo_provider",
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def auth_user(provider_user):
    return User.objects.create_user(
        username=f"telegram_{provider_user.telegram_id}",
    )


@pytest.fixture
def other_auth_user(other_provider_user):
    return User.objects.create_user(
        username=f"telegram_{other_provider_user.telegram_id}",
    )


@pytest.fixture
def token(auth_user):
    token, _ = Token.objects.get_or_create(user=auth_user)
    return token


@pytest.fixture
def other_token(other_auth_user):
    token, _ = Token.objects.get_or_create(user=other_auth_user)
    return token


@pytest.fixture
def authenticated_client(api_client, token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )
    return api_client


@pytest.fixture
def other_authenticated_client(api_client, other_token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {other_token.key}"
    )
    return api_client


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Photo API Category"
    )


@pytest.fixture
def service(provider_user, category):
    return ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Photo API Service",
        description="Photo API Service Description",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )


@pytest.fixture
def other_service(other_provider_user, category):
    return ServiceProfile.objects.create(
        provider=other_provider_user,
        category=category,
        title="Other Photo API Service",
        description="Other Photo API Service Description",
        city_text="Adama",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
    )


@pytest.mark.django_db
def test_add_service_photo(authenticated_client, service):
    response = authenticated_client.post(
        "/api/service/photos/",
        {
            "telegram_file_id": "telegram_file_1",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["success"] is True
    assert response.data["photo"]["telegram_file_id"] == "telegram_file_1"
    assert response.data["photo"]["order_index"] == 1
    assert service.photos.count() == 1


@pytest.mark.django_db
def test_add_three_service_photos(authenticated_client, service):
    for index in range(1, 4):
        response = authenticated_client.post(
            "/api/service/photos/",
            {
                "telegram_file_id": f"telegram_file_{index}",
            },
            format="json",
        )

        assert response.status_code == 201

    assert service.photos.count() == 3


@pytest.mark.django_db
def test_fourth_photo_is_rejected(authenticated_client, service):
    for index in range(1, 4):
        ServicePhoto.objects.create(
            service=service,
            telegram_file_id=f"existing_file_{index}",
            order_index=index,
        )

    response = authenticated_client.post(
        "/api/service/photos/",
        {
            "telegram_file_id": "telegram_file_4",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False
    assert service.photos.count() == 3


@pytest.mark.django_db
def test_add_photo_requires_service(authenticated_client):
    response = authenticated_client.post(
        "/api/service/photos/",
        {
            "telegram_file_id": "telegram_file_1",
        },
        format="json",
    )

    assert response.status_code == 404
    assert response.data["success"] is False


@pytest.mark.django_db
def test_add_photo_rejects_duplicate_order_index(authenticated_client, service):
    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="existing_file",
        order_index=1,
    )

    response = authenticated_client.post(
        "/api/service/photos/",
        {
            "telegram_file_id": "new_file",
            "order_index": 1,
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False


@pytest.mark.django_db
def test_delete_own_service_photo(authenticated_client, service):
    photo = ServicePhoto.objects.create(
        service=service,
        telegram_file_id="telegram_file_1",
        order_index=1,
    )

    response = authenticated_client.delete(
        f"/api/service/photos/{photo.id}/"
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["deleted"] is True
    assert ServicePhoto.objects.filter(id=photo.id).exists() is False


@pytest.mark.django_db
def test_delete_another_users_photo_is_rejected(
    authenticated_client,
    other_service,
):
    photo = ServicePhoto.objects.create(
        service=other_service,
        telegram_file_id="other_file",
        order_index=1,
    )

    response = authenticated_client.delete(
        f"/api/service/photos/{photo.id}/"
    )

    assert response.status_code == 403
    assert response.data["success"] is False
    assert ServicePhoto.objects.filter(id=photo.id).exists() is True


@pytest.mark.django_db
def test_delete_missing_photo_returns_404(authenticated_client, service):
    response = authenticated_client.delete(
        "/api/service/photos/999999/"
    )

    assert response.status_code == 404
    assert response.data["success"] is False