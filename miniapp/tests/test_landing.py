import pytest


@pytest.mark.django_db
def test_miniapp_root_landing_page(api_client):
    response = api_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]
    assert b"Marketplace" in response.content
    assert b"Loading Marketplace" in response.content


@pytest.mark.django_db
def test_api_miniapp_landing_page(api_client):
    response = api_client.get("/api/miniapp/")

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]
    assert b"Marketplace" in response.content


@pytest.mark.django_db
def test_favicon_returns_empty_success(api_client):
    response = api_client.get("/favicon.ico")

    assert response.status_code == 204
