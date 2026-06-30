import math
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from approvals.models import AdminSettings
from matching.views import (
    _compute_service_scores,
    RECENT_REQUEST_WINDOW_DAYS,
    PRICE_FLOOR,
    PRICE_CEILING,
    LIKES_REFERENCE,
    DISCOVERY_GRADE_PERIOD_DAYS,
)
from services.models import (
    ServiceCategory,
    ServicePhoto,
    ServicePrice,
    ServiceProfile,
)
from swipes.models import SwipeHistory


@pytest.fixture
def customer():
    return TelegramUser.objects.create(
        telegram_id=77701,
        role=TelegramUser.Role.CUSTOMER,
        customer_latitude=Decimal("9.03"),
        customer_longitude=Decimal("38.74"),
    )


@pytest.fixture
def provider():
    return TelegramUser.objects.create(
        telegram_id=77702,
        role=TelegramUser.Role.PROVIDER,
        telegram_username="hidden_provider",
        phone_number="+251900000000",
    )


@pytest.fixture
def auth_user(customer):
    return User.objects.create_user(
        username=f"telegram_{customer.telegram_id}",
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
def electrician_category():
    return ServiceCategory.objects.create(
        name="Electrician"
    )


@pytest.fixture
def cleaner_category():
    return ServiceCategory.objects.create(
        name="Cleaner"
    )


@pytest.fixture
def approved_service(provider, electrician_category):
    service = ServiceProfile.objects.create(
        provider=provider,
        category=electrician_category,
        title="Approved Electrician",
        description="Electrical repair service",
        city_text="Addis Ababa",
        latitude="9.030000",
        longitude="38.740000",
        location_source=ServiceProfile.LocationSource.BOTH,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )

    ServicePrice.objects.create(
        service=service,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount="500.00",
    )

    ServicePhoto.objects.create(
        service=service,
        telegram_file_id="photo_file_1",
        order_index=1,
    )

    return service


@pytest.mark.django_db
def test_swipe_returns_one_approved_visible_card(authenticated_client, approved_service):
    response = authenticated_client.get(
        "/api/discovery/swipe/",
        {
            "category_id": approved_service.category_id,
            "city_text": "Addis Ababa",
        },
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["card"]["id"] == approved_service.id
    assert response.data["card"]["title"] == "Approved Electrician"


@pytest.mark.django_db
def test_grid_returns_paginated_results(authenticated_client, approved_service):
    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": approved_service.category_id,
            "city_text": "Addis Ababa",
            "page": 1,
            "page_size": 10,
        },
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == approved_service.id


@pytest.mark.django_db
def test_discovery_filters_out_unapproved_service(
    authenticated_client,
    provider,
    electrician_category,
):
    ServiceProfile.objects.create(
        provider=provider,
        category=electrician_category,
        title="Pending Electrician",
        description="Pending service",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.PENDING,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )

    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": electrician_category.id,
            "city_text": "Addis Ababa",
        },
    )

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_discovery_filters_out_hidden_service(
    authenticated_client,
    provider,
    electrician_category,
):
    ServiceProfile.objects.create(
        provider=provider,
        category=electrician_category,
        title="Hidden Electrician",
        description="Hidden service",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.OFF,
    )

    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": electrician_category.id,
            "city_text": "Addis Ababa",
        },
    )

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_discovery_filters_by_category(
    authenticated_client,
    provider,
    electrician_category,
    cleaner_category,
):
    ServiceProfile.objects.create(
        provider=provider,
        category=cleaner_category,
        title="Cleaner Service",
        description="Cleaner service",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )

    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": electrician_category.id,
            "city_text": "Addis Ababa",
        },
    )

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_discovery_filters_by_city(authenticated_client, approved_service):
    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": approved_service.category_id,
            "city_text": "Adama",
        },
    )

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_discovery_uses_gps_distance(authenticated_client, approved_service):
    AdminSettings.get_settings()

    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": approved_service.category_id,
            "latitude": "9.031000",
            "longitude": "38.741000",
        },
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["count"] == 1
    assert response.data["results"][0]["distance_km"] is not None


@pytest.mark.django_db
def test_discovery_excludes_no_gps_when_gps_filter_used(
    authenticated_client,
    provider,
    electrician_category,
):
    ServiceProfile.objects.create(
        provider=provider,
        category=electrician_category,
        title="City Only Service",
        description="City only service",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )

    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": electrician_category.id,
            "latitude": "9.031000",
            "longitude": "38.741000",
        },
    )

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_discovery_excludes_recently_seen_service(
    authenticated_client,
    customer,
    approved_service,
):
    SwipeHistory.objects.create(
        customer=customer,
        service=approved_service,
        swipe_status=SwipeHistory.SwipeStatus.SEEN,
    )

    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": approved_service.category_id,
            "city_text": "Addis Ababa",
        },
    )

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_discovery_response_does_not_expose_private_data(
    authenticated_client,
    approved_service,
):
    response = authenticated_client.get(
        "/api/discovery/swipe/",
        {
            "category_id": approved_service.category_id,
            "city_text": "Addis Ababa",
        },
    )

    card = response.data["card"]
    serialized = str(card)

    assert "phone_number" not in card
    assert "telegram_username" not in card
    assert "latitude" not in card
    assert "longitude" not in card
    assert "+251900000000" not in serialized
    assert "provider_name" in card
    assert "provider_is_verified" in card
    assert "provider_admin_tested_badge" in card
    assert "is_verified" in card
    assert "admin_tested_badge" in card
    assert "likes_count" in card


@pytest.mark.django_db
def test_discovery_response_includes_requested_badge_fields(
    authenticated_client,
    provider,
    approved_service,
):
    provider.is_verified = True
    provider.admin_tested_badge = True
    provider.save(update_fields=["is_verified", "admin_tested_badge", "updated_at"])
    approved_service.likes_count = 31
    approved_service.save(update_fields=["likes_count", "updated_at"])

    response = authenticated_client.get(
        "/api/discovery/grid/",
        {
            "category_id": approved_service.category_id,
            "city_text": "Addis Ababa",
        },
    )

    card = response.data["results"][0]

    assert card["is_verified"] is True
    assert card["admin_tested_badge"] is True
    assert card["provider_is_verified"] is True
    assert card["provider_admin_tested_badge"] is True
    assert card["likes_count"] == 31


@pytest.mark.django_db
def test_swipe_can_exclude_current_card_for_prefetch(
    authenticated_client,
    electrician_category,
    approved_service,
):
    second_provider = TelegramUser.objects.create(
        telegram_id=77703,
        role=TelegramUser.Role.PROVIDER,
        telegram_username="second_provider",
        phone_number="+251900000001",
    )
    second_service = ServiceProfile.objects.create(
        provider=second_provider,
        category=electrician_category,
        title="Second Electrician",
        description="Second service",
        city_text="Addis Ababa",
        latitude="9.030500",
        longitude="38.740500",
        location_source=ServiceProfile.LocationSource.BOTH,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )

    response = authenticated_client.get(
        "/api/discovery/swipe/",
        {
            "category_id": electrician_category.id,
            "city_text": "Addis Ababa",
            "exclude_service_id": approved_service.id,
        },
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["card"]["id"] == second_service.id


# ─── Scoring unit tests ────────────────────────────────────────────────

@pytest.fixture
def admin_settings():
    return AdminSettings.get_settings()


@pytest.fixture
def score_customer():
    return TelegramUser.objects.create(
        telegram_id=88801,
        role=TelegramUser.Role.CUSTOMER,
    )


@pytest.fixture
def score_provider():
    return TelegramUser.objects.create(
        telegram_id=88802,
        role=TelegramUser.Role.PROVIDER,
        telegram_username="score_provider",
        phone_number="+251911111111",
    )


@pytest.fixture
def score_category():
    return ServiceCategory.objects.create(name="Scoring")


def _make_priced_service(provider, category, title, price_amount, likes=0, days_old=0):
    service = ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title=title,
        description=title,
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=ServiceProfile.ApprovalStatus.APPROVED,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
        likes_count=likes,
    )
    if days_old:
        ServiceProfile.objects.filter(pk=service.pk).update(
            created_at=timezone.now() - timedelta(days=days_old)
        )
        service.refresh_from_db()
    ServicePrice.objects.create(
        service=service,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount=str(price_amount),
    )
    return service


@pytest.mark.django_db
class TestComputeServiceScores:
    def test_proximity_zero_when_no_distance(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "Svc", 5000)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        assert result["live_score"] < 66  # stored max = 65, proximity = 0
        assert not result["price_flagged"]

    def test_price_flagged_when_below_floor(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "Cheap", PRICE_FLOOR - 1)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        assert result["price_flagged"]

    def test_price_flagged_when_above_ceiling(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "Expensive", PRICE_CEILING + 1)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        assert result["price_flagged"]

    def test_price_not_flagged_when_within_range(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "Normal", 5000)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        assert not result["price_flagged"]

    def test_quality_score_zero_for_no_likes(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "No likes", 5000, likes=0)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        # stored = quality(0) + price(15) + demand(10) + fresh(10) = 35
        assert result["live_score"] == pytest.approx(35.0, abs=0.1)

    def test_quality_scales_with_likes(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "Popular", 5000, likes=50)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        expected_quality = min(1.0, math.log1p(50) / math.log1p(LIKES_REFERENCE)) * 30.0
        expected_stored = expected_quality + 15 + 10 + 10
        assert result["live_score"] == pytest.approx(expected_stored, abs=0.1)

    def test_demand_score_drops_with_recent_reqs(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "Demanded", 5000)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={score_provider.id: 5},
            current_time=timezone.now(),
        )
        # demand = max(0, 10 - 5) = 5
        expected_stored = 0 + 15 + 5 + 10  # quality 0 + price 15 + demand 5 + fresh 10
        assert result["live_score"] == pytest.approx(expected_stored, abs=0.1)

    def test_demand_score_floors_at_zero(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "High demand", 5000)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={score_provider.id: 20},
            current_time=timezone.now(),
        )
        # demand = max(0, 10 - min(10, 20)) = 0
        expected_stored = 0 + 15 + 0 + 10
        assert result["live_score"] == pytest.approx(expected_stored, abs=0.1)

    def test_freshness_decreases_with_age(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "Old", 5000, days_old=15)
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        expected_fresh = max(0.0, 10.0 - 15.0 / 30.0)  # = 9.5
        expected_stored = 0 + 15 + 10 + expected_fresh
        assert result["live_score"] == pytest.approx(expected_stored, abs=0.3)

    def test_grade_period_forced_freshness_10(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(
            score_provider, score_category, "New grade",
            price_amount=5000, likes=0, days_old=DISCOVERY_GRADE_PERIOD_DAYS - 1,
        )
        result = _compute_service_scores(
            service=service,
            distance_km=None,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        # Grade period: liked=0 & age <= 7d → freshness forced to 10
        expected_stored = 0 + 15 + 10 + 10
        assert result["live_score"] == pytest.approx(expected_stored, abs=0.1)

    def test_proximity_adds_to_live_score(self, score_provider, score_category, admin_settings):
        service = _make_priced_service(score_provider, score_category, "Close", 5000)
        result = _compute_service_scores(
            service=service,
            distance_km=1.0,
            admin_settings=admin_settings,
            avg_prices_by_category={},
            recent_reqs_by_provider={},
            current_time=timezone.now(),
        )
        # proximity = max(0, 1 - 1/10) * 35 = 31.5
        # stored = 0 + 15 + 10 + 10 = 35
        expected = 35.0 + 31.5
        assert result["live_score"] == pytest.approx(expected, abs=0.5)


@pytest.mark.django_db
class TestDiscoverySortingOrder:
    def test_price_flagged_services_sorted_last(self, authenticated_client, score_category, electrician_category):
        """Services with prices outside [1000,20000] appear after in-range services."""
        provider1 = TelegramUser.objects.create(
            telegram_id=88901, role=TelegramUser.Role.PROVIDER,
            telegram_username="p1", phone_number="+251900001",
        )
        provider2 = TelegramUser.objects.create(
            telegram_id=88902, role=TelegramUser.Role.PROVIDER,
            telegram_username="p2", phone_number="+251900002",
        )

        in_range = _make_priced_service(provider1, electrician_category, "In Range", 5000)
        out_of_range = _make_priced_service(provider2, electrician_category, "Too Cheap", PRICE_FLOOR - 1)

        response = authenticated_client.get(
            "/api/discovery/grid/",
            {"category_id": electrician_category.id, "city_text": "Addis Ababa"},
        )
        assert response.status_code == 200
        ids = [r["id"] for r in response.data["results"]]
        assert ids == [in_range.id, out_of_range.id]

    def test_higher_score_service_comes_first(self, authenticated_client, score_category, electrician_category):
        """Service with more likes (higher quality) ranks above one with fewer."""
        provider1 = TelegramUser.objects.create(
            telegram_id=88903, role=TelegramUser.Role.PROVIDER,
            telegram_username="p3", phone_number="+251900003",
        )
        provider2 = TelegramUser.objects.create(
            telegram_id=88904, role=TelegramUser.Role.PROVIDER,
            telegram_username="p4", phone_number="+251900004",
        )

        less_popular = _make_priced_service(provider1, electrician_category, "Less Popular", 5000, likes=1)
        more_popular = _make_priced_service(provider2, electrician_category, "More Popular", 5000, likes=50)

        response = authenticated_client.get(
            "/api/discovery/grid/",
            {"category_id": electrician_category.id, "city_text": "Addis Ababa"},
        )
        assert response.status_code == 200
        ids = [r["id"] for r in response.data["results"]]
        assert ids == [more_popular.id, less_popular.id]

    def test_new_service_with_zero_likes_appears_via_scoring(self, authenticated_client, score_category, electrician_category):
        """New service with 0 likes still gets a base score and appears."""
        provider = TelegramUser.objects.create(
            telegram_id=88905, role=TelegramUser.Role.PROVIDER,
            telegram_username="p5", phone_number="+251900005",
        )
        new_svc = _make_priced_service(provider, electrician_category, "New", 5000, likes=0)
        response = authenticated_client.get(
            "/api/discovery/grid/",
            {"category_id": electrician_category.id, "city_text": "Addis Ababa"},
        )
        assert response.status_code == 200
        ids = [r["id"] for r in response.data["results"]]
        assert new_svc.id in ids
