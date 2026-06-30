import pytest


@pytest.mark.django_db
def test_health_endpoint_still_works(api_client):
    response = api_client.get("/api/health/")

    assert response.status_code == 200
    assert response.data["success"] is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url,app_name",
    [
        ("/api/accounts/", "accounts"),
        ("/api/services/", "services"),
        ("/api/swipes/", "swipes"),
        ("/api/matching/", "matching"),
        ("/api/approvals/", "approvals"),
        ("/api/moderation/", "moderation"),
        ("/api/verification/", "verification"),
        ("/api/miniapp/route-check/", "miniapp"),
        ("/api/adminpanel/", "adminpanel"),
    ],
)
def test_api_app_route_checks_do_not_crash(api_client, url, app_name):
    response = api_client.get(url)

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["app"] == app_name
