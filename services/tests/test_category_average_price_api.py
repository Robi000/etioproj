from decimal import Decimal

import pytest

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServicePrice, ServiceProfile


def make_provider(telegram_id: int) -> TelegramUser:
    return TelegramUser.objects.create(
        telegram_id=telegram_id,
        role=TelegramUser.Role.PROVIDER,
        telegram_username=f"provider_{telegram_id}",
        phone_number="+251900000000",
    )


def make_service(
    provider: TelegramUser,
    category: ServiceCategory,
    title: str,
    approval_status: str = ServiceProfile.ApprovalStatus.APPROVED,
) -> ServiceProfile:
    return ServiceProfile.objects.create(
        provider=provider,
        category=category,
        title=title,
        description="Reliable provider with clear service pricing.",
        city_text="Addis Ababa",
        location_source=ServiceProfile.LocationSource.CITY_TEXT,
        approval_status=approval_status,
        visibility_status=ServiceProfile.VisibilityStatus.ON,
    )


@pytest.mark.django_db
def test_category_average_price_returns_approved_service_averages(api_client):
    category = ServiceCategory.objects.create(name="Cleaner")
    first_service = make_service(make_provider(81001), category, "First Cleaner")
    second_service = make_service(make_provider(81002), category, "Second Cleaner")
    pending_service = make_service(
        make_provider(81003),
        category,
        "Pending Cleaner",
        approval_status=ServiceProfile.ApprovalStatus.PENDING,
    )

    ServicePrice.objects.create(
        service=first_service,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount=Decimal("1000.00"),
    )
    ServicePrice.objects.create(
        service=second_service,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount=Decimal("1500.00"),
    )
    ServicePrice.objects.create(
        service=first_service,
        price_type=ServicePrice.PriceType.FULL_DAY,
        amount=Decimal("2100.00"),
    )
    ServicePrice.objects.create(
        service=second_service,
        price_type=ServicePrice.PriceType.NIGHT,
        amount=Decimal("1800.00"),
    )
    ServicePrice.objects.create(
        service=pending_service,
        price_type=ServicePrice.PriceType.HALF_DAY,
        amount=Decimal("9000.00"),
    )

    response = api_client.get(
        "/api/services/category-avg-price/",
        {"category_id": category.id},
    )

    assert response.status_code == 200
    assert response.data == {
        "success": True,
        "category_id": category.id,
        "category_name": "Cleaner",
        "averages": {
            "half_day": "1250.00",
            "full_day": "2100.00",
            "night": "1800.00",
        },
    }


@pytest.mark.django_db
def test_category_average_price_requires_positive_category_id(api_client):
    response = api_client.get("/api/services/category-avg-price/")

    assert response.status_code == 400
    assert response.data["success"] is False
