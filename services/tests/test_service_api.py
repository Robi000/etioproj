import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServiceProfile


@pytest.fixture
def provider_user():
    return TelegramUser.objects.create(
        telegram_id=44444,
        telegram_username="provider_api",
        first_name="Provider",
        phone_number="+251911111111",
        role=TelegramUser.Role.PROVIDER,
    )


@pytest.fixture
def customer_user():
    return TelegramUser.objects.create(
        telegram_id=44445,
        telegram_username="customer_api",
        first_name="Customer",
        role=TelegramUser.Role.CUSTOMER,
    )


@pytest.fixture
def auth_user(provider_user):
    return User.objects.create_user(
        username=f"telegram_{provider_user.telegram_id}",
        first_name=provider_user.first_name,
    )


@pytest.fixture
def customer_auth_user(customer_user):
    return User.objects.create_user(
        username=f"telegram_{customer_user.telegram_id}",
        first_name=customer_user.first_name,
    )


@pytest.fixture
def token(auth_user):
    token, _ = Token.objects.get_or_create(user=auth_user)
    return token


@pytest.fixture
def customer_token(customer_auth_user):
    token, _ = Token.objects.get_or_create(user=customer_auth_user)
    return token


@pytest.fixture
def authenticated_client(api_client, token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )
    return api_client


@pytest.fixture
def customer_client(api_client, customer_token):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Token {customer_token.key}"
    )
    return api_client


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="Service API Category"
    )


@pytest.fixture
def second_category():
    return ServiceCategory.objects.create(
        name="Second API Category"
    )


@pytest.mark.django_db
def test_provider_can_create_service(authenticated_client, category, provider_user):
    response = authenticated_client.post(
        "/api/service/",
        {
            "category_id": category.id,
            "title": "Electrical Service",
            "description": "Professional electrical service.",
            "city_text": "Addis Ababa",
            "visibility_status": ServiceProfile.VisibilityStatus.ON,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["success"] is True
    assert response.data["service"]["title"] == "Electrical Service"
    assert response.data["service"]["approval_status"] == ServiceProfile.ApprovalStatus.PENDING
    assert ServiceProfile.objects.filter(provider=provider_user).count() == 1


@pytest.mark.django_db
def test_customer_cannot_create_service(customer_client, category):
    response = customer_client.post(
        "/api/service/",
        {
            "category_id": category.id,
            "title": "Invalid Service",
            "description": "Should not be created.",
            "city_text": "Addis Ababa",
        },
        format="json",
    )

    assert response.status_code == 403
    assert response.data["success"] is False


@pytest.mark.django_db
def test_provider_cannot_create_two_services(authenticated_client, category):
    payload = {
        "category_id": category.id,
        "title": "First Service",
        "description": "First service description.",
        "city_text": "Addis Ababa",
    }

    first_response = authenticated_client.post(
        "/api/service/",
        payload,
        format="json",
    )

    second_response = authenticated_client.post(
        "/api/service/",
        {
            **payload,
            "title": "Second Service",
        },
        format="json",
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 400
    assert second_response.data["success"] is False


@pytest.mark.django_db
def test_get_my_service(authenticated_client, category):
    create_response = authenticated_client.post(
        "/api/service/",
        {
            "category_id": category.id,
            "title": "Readable Service",
            "description": "Readable description.",
            "city_text": "Addis Ababa",
        },
        format="json",
    )

    response = authenticated_client.get("/api/service/me/")

    assert create_response.status_code == 201
    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["service"]["title"] == "Readable Service"


@pytest.mark.django_db
def test_get_my_service_includes_rejection_reason(authenticated_client, category, provider_user):
    ServiceProfile.objects.create(
        provider=provider_user,
        category=category,
        title="Rejected Service",
        description="Rejected description.",
        city_text="Addis Ababa",
        approval_status=ServiceProfile.ApprovalStatus.REJECTED,
        rejection_reason="Photos are unclear.",
    )

    response = authenticated_client.get("/api/service/me/")

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["service"]["approval_status"] == ServiceProfile.ApprovalStatus.REJECTED
    assert response.data["service"]["rejection_reason"] == "Photos are unclear."


@pytest.mark.django_db
def test_get_my_service_returns_404_when_missing(authenticated_client):
    response = authenticated_client.get("/api/service/me/")

    assert response.status_code == 404
    assert response.data["success"] is False


@pytest.mark.django_db
def test_update_my_service(authenticated_client, category, second_category):
    authenticated_client.post(
        "/api/service/",
        {
            "category_id": category.id,
            "title": "Old Service",
            "description": "Old description.",
            "city_text": "Addis Ababa",
        },
        format="json",
    )

    response = authenticated_client.patch(
        "/api/service/me/update/",
        {
            "category_id": second_category.id,
            "title": "Updated Service",
            "description": "Updated description.",
            "city_text": "Adama",
            "visibility_status": ServiceProfile.VisibilityStatus.OFF,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["service"]["title"] == "Updated Service"
    assert response.data["service"]["category"]["id"] == second_category.id
    assert response.data["service"]["visibility_status"] == ServiceProfile.VisibilityStatus.OFF


@pytest.mark.django_db
def test_update_my_service_rejects_invalid_coordinates(authenticated_client, category):
    authenticated_client.post(
        "/api/service/",
        {
            "category_id": category.id,
            "title": "Location Service",
            "description": "Location description.",
            "city_text": "Addis Ababa",
        },
        format="json",
    )

    response = authenticated_client.patch(
        "/api/service/me/update/",
        {
            "latitude": "120.000000",
            "longitude": "38.740000",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False


@pytest.mark.django_db
def test_delete_my_service_hard_deletes(authenticated_client, category, provider_user):
    authenticated_client.post(
        "/api/service/",
        {
            "category_id": category.id,
            "title": "Delete Service",
            "description": "Delete description.",
            "city_text": "Addis Ababa",
        },
        format="json",
    )

    response = authenticated_client.delete("/api/service/me/delete/")

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["delete_behavior"] == "hard_delete"
    assert ServiceProfile.objects.filter(provider=provider_user).exists() is False


@pytest.mark.django_db
def test_delete_my_service_returns_404_when_missing(authenticated_client):
    response = authenticated_client.delete("/api/service/me/delete/")

    assert response.status_code == 404
    assert response.data["success"] is False
