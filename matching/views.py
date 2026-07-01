import logging
import math
import random
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.views import get_telegram_user_from_auth_user
from approvals.models import AdminSettings, ContactRequest
from approvals.usage_limits import build_contact_usage_payload, evaluate_contact_request_creation
from bot.location import LOCATION_REQUEST_TEXT
from services.models import ServicePrice, ServiceProfile
from swipes.models import SwipeHistory

from .serializers import DiscoveryServiceCardSerializer, build_discovery_card

logger = logging.getLogger("marketplace")


@api_view(["GET"])
@permission_classes([AllowAny])
def matching_route_check(request: Request) -> Response:
    logger.info("Matching API route check requested.")
    return Response(
        {
            "success": True,
            "app": "matching",
            "message": "Matching API route is available.",
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def discovery_swipe(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    filters = parse_discovery_filters(request)

    if filters["error"]:
        return Response(
            {
                "success": False,
                "error": filters["error"],
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    latitude = filters["latitude"]
    longitude = filters["longitude"]
    city_text = filters["city_text"]

    if latitude is None and longitude is None and not city_text:
        latitude, longitude = resolve_discovery_coordinates(telegram_user)

    if latitude is None and longitude is None and not telegram_user.has_customer_location and not city_text:
        return location_required_response()

    batch_size = parse_positive_int(request.query_params.get("batch_size"), default=1)
    batch_size = min(max(batch_size or 1, 1), 6)

    services = get_discovery_services(
        customer=telegram_user,
        category_id=filters["category_id"],
        city_text=city_text,
        latitude=latitude,
        longitude=longitude,
        exclude_service_ids=filters["exclude_service_ids"],
        apply_exploration=True,
        card_limit=batch_size,
    )

    usage_decision = evaluate_contact_request_creation(telegram_user)

    if not services:
        return Response(
            {
                "success": True,
                "card": None,
                "cards": [],
                "message": "No matching service found.",
                "provider_protection": build_contact_usage_payload(usage_decision),
            },
            status=status.HTTP_200_OK,
        )

    cards = [item["card"] for item in services[:batch_size]]
    card = cards[0]

    return Response(
        {
            "success": True,
            "card": card,
            "cards": cards,
            "provider_protection": build_contact_usage_payload(usage_decision),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def discovery_grid(request: Request) -> Response:
    telegram_user = get_telegram_user_from_auth_user(request.user)

    if telegram_user is None:
        return linked_user_not_found_response()

    filters = parse_discovery_filters(request)

    if filters["error"]:
        return Response(
            {
                "success": False,
                "error": filters["error"],
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    latitude = filters["latitude"]
    longitude = filters["longitude"]
    city_text = filters["city_text"]

    if latitude is None and longitude is None and not city_text:
        latitude, longitude = resolve_discovery_coordinates(telegram_user)

    if latitude is None and longitude is None and not telegram_user.has_customer_location and not city_text:
        return location_required_response()

    page = parse_positive_int(request.query_params.get("page"), default=1)
    page_size = parse_positive_int(request.query_params.get("page_size"), default=10)

    if page_size > 50:
        page_size = 50

    services = get_discovery_services(
        customer=telegram_user,
        category_id=filters["category_id"],
        city_text=city_text,
        latitude=latitude,
        longitude=longitude,
        exclude_service_ids=filters["exclude_service_ids"],
    )

    total = len(services)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = services[start:end]

    return Response(
        {
            "success": True,
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": [item["card"] for item in page_items],
        },
        status=status.HTTP_200_OK,
    )


def parse_discovery_filters(request: Request) -> dict:
    category_id = request.query_params.get("category_id")
    city_text = request.query_params.get("city_text", "").strip()
    latitude = request.query_params.get("latitude")
    longitude = request.query_params.get("longitude")
    exclude_service_ids = request.query_params.get("exclude_service_ids")
    exclude_service_id = request.query_params.get("exclude_service_id")

    parsed_category_id = None
    parsed_latitude = None
    parsed_longitude = None
    parsed_exclude_service_ids: list[int] = []

    if category_id:
        parsed_category_id = parse_positive_int(category_id, default=None)

        if parsed_category_id is None:
            return {
                "error": "category_id must be a positive integer.",
                "category_id": None,
                "city_text": "",
                "latitude": None,
                "longitude": None,
                "exclude_service_ids": [],
            }

    raw_exclude_ids = []
    if exclude_service_ids:
        raw_exclude_ids.extend(
            item.strip() for item in exclude_service_ids.split(",") if item.strip()
        )
    if exclude_service_id:
        raw_exclude_ids.append(exclude_service_id.strip())

    for raw_id in raw_exclude_ids:
        parsed_id = parse_positive_int(raw_id, default=None)
        if parsed_id is None:
            return {
                "error": "exclude_service_ids must contain positive integers.",
                "category_id": None,
                "city_text": "",
                "latitude": None,
                "longitude": None,
                "exclude_service_ids": [],
            }
        parsed_exclude_service_ids.append(parsed_id)

    if bool(latitude) != bool(longitude):
        return {
            "error": "latitude and longitude must be provided together.",
            "category_id": None,
            "city_text": "",
            "latitude": None,
            "longitude": None,
            "exclude_service_ids": [],
        }

    if latitude and longitude:
        try:
            parsed_latitude = Decimal(latitude)
            parsed_longitude = Decimal(longitude)
        except InvalidOperation:
            return {
                "error": "latitude and longitude must be valid decimal numbers.",
                "category_id": None,
                "city_text": "",
                "latitude": None,
                "longitude": None,
                "exclude_service_ids": [],
            }

        if parsed_latitude < Decimal("-90") or parsed_latitude > Decimal("90"):
            return {
                "error": "latitude must be between -90 and 90.",
                "category_id": None,
                "city_text": "",
                "latitude": None,
                "longitude": None,
                "exclude_service_ids": [],
            }

        if parsed_longitude < Decimal("-180") or parsed_longitude > Decimal("180"):
            return {
                "error": "longitude must be between -180 and 180.",
                "category_id": None,
                "city_text": "",
                "latitude": None,
                "longitude": None,
                "exclude_service_ids": [],
            }

    return {
        "error": None,
        "category_id": parsed_category_id,
        "city_text": city_text,
        "latitude": parsed_latitude,
        "longitude": parsed_longitude,
        "exclude_service_ids": parsed_exclude_service_ids,
    }


DISCOVERY_GRADE_PERIOD_DAYS = 7
RECENT_REQUEST_WINDOW_DAYS = 7
EXPLORATION_INTERVAL = 5
PRICE_FLOOR = 1000
PRICE_CEILING = 50000
LIKES_REFERENCE = 200


def get_discovery_services(
    customer,
    category_id: int | None,
    city_text: str,
    latitude: Decimal | None,
    longitude: Decimal | None,
    exclude_service_ids: list[int] | None = None,
    apply_exploration: bool = False,
    card_limit: int | None = None,
) -> list[dict]:
    admin_settings = AdminSettings.get_settings()
    current_time = timezone.now()

    if getattr(settings, 'DEBUG', False):
        recently_seen_service_ids = SwipeHistory.objects.none().values_list("service_id", flat=True)
    else:
        recently_seen_service_ids = SwipeHistory.objects.filter(
            customer=customer,
            reset_at__gt=current_time,
        ).values_list("service_id", flat=True)

    queryset = (
        ServiceProfile.objects.select_related(
            "provider",
            "category",
        )
        .prefetch_related(
            "prices",
            "photos",
        )
        .filter(
            approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
            provider__is_banned=False,
            category__active=True,
            admin_forced_hidden=False,
        )
        .filter(
            Q(penalty_until__isnull=True) | Q(penalty_until__lt=timezone.now())
        )
        .exclude(
            id__in=recently_seen_service_ids,
        )
    )

    if exclude_service_ids:
        queryset = queryset.exclude(id__in=exclude_service_ids)

    if category_id is not None:
        queryset = queryset.filter(category_id=category_id)

    category_ids = set(queryset.values_list("category_id", flat=True))
    avg_prices_by_category = _compute_avg_prices_per_category(category_ids)

    recent_cutoff = current_time - timedelta(days=RECENT_REQUEST_WINDOW_DAYS)
    recent_reqs_by_provider = dict(
        ContactRequest.objects.filter(
            provider_id__in=set(queryset.values_list("provider_id", flat=True)),
            created_at__gte=recent_cutoff,
        ).values_list("provider_id").annotate(count=Count("id"))
    )

    service_rows = []

    for service in queryset:
        distance_km = calculate_distance_if_possible(
            latitude=latitude,
            longitude=longitude,
            service=service,
        )

        if latitude is not None and longitude is not None:
            if distance_km is None:
                continue
            if distance_km > admin_settings.default_radius:
                continue
        elif city_text:
            if normalize_city(service.city_text) != normalize_city(city_text):
                continue

        scores = _compute_service_scores(
            service=service,
            distance_km=distance_km,
            admin_settings=admin_settings,
            avg_prices_by_category=avg_prices_by_category,
            recent_reqs_by_provider=recent_reqs_by_provider,
            current_time=current_time,
        )

        service_rows.append({
            "service": service,
            "distance_km": distance_km,
            "is_own": service.provider_id == customer.id,
            "live_score": scores["live_score"],
            "price_flagged": scores["price_flagged"],
        })

    service_rows.sort(
        key=lambda item: (
            item["price_flagged"],
            -item["live_score"],
        )
    )

    if apply_exploration and len(service_rows) >= EXPLORATION_INTERVAL + 1:
        _inject_exploration(service_rows)

    if card_limit is None:
        card_materialization_rows = service_rows
    else:
        card_materialization_rows = service_rows[:max(0, card_limit)]

    for row in card_materialization_rows:
        card = build_discovery_card(
            service=row["service"],
            distance_km=row["distance_km"],
            is_own=row["is_own"],
        )
        serializer = DiscoveryServiceCardSerializer(data=card)
        serializer.is_valid(raise_exception=True)
        row["card"] = serializer.validated_data

    return service_rows


def _compute_avg_prices_per_category(category_ids: set) -> dict[int, Decimal]:
    if not category_ids:
        return {}
    from django.db.models import Avg
    prices_qs = (
        ServicePrice.objects
        .filter(service__category_id__in=category_ids)
        .values("service__category_id")
        .annotate(avg_amount=Avg("amount"))
    )
    return {p["service__category_id"]: p["avg_amount"] for p in prices_qs}


def _compute_service_scores(
    service,
    distance_km: float | None,
    admin_settings,
    avg_prices_by_category: dict,
    recent_reqs_by_provider: dict,
    current_time,
) -> dict:
    radius = float(admin_settings.default_radius)

    # Proximity (0-35)
    if distance_km is not None and radius > 0:
        proximity_score = max(0.0, 1.0 - distance_km / radius) * 35.0
    else:
        proximity_score = 0.0

    # Quality (0-30)
    likes = service.likes_count or 0
    quality_score = min(1.0, math.log1p(likes) / math.log1p(LIKES_REFERENCE)) * 30.0

    # Price (0-15) — bell curve: max at midpoint, decreases toward both ends
    price_flag = False
    price_score = 0.0
    prices = list(service.prices.all())
    if prices:
        amounts = [Decimal(str(p.amount)) for p in prices]
        avg_price = float(sum(amounts) / len(amounts))
        if avg_price < PRICE_FLOOR or avg_price > PRICE_CEILING:
            price_flag = True
        else:
            price_mid = (PRICE_FLOOR + PRICE_CEILING) / 2.0
            price_half_range = price_mid - PRICE_FLOOR
            price_score = 15.0 * max(0.0, 1.0 - abs(avg_price - price_mid) / price_half_range)

    # Demand-Fairness (0-10)
    recent_reqs = recent_reqs_by_provider.get(service.provider_id, 0)
    demand_score = max(0.0, 10.0 - min(10.0, float(recent_reqs)))

    # Freshness (0-10)
    days_old = max(0.0, (current_time - service.created_at).total_seconds() / 86400.0)
    freshness_score = max(0.0, 10.0 - days_old / 30.0)

    # Grade period: likes_count=0 and newly created → force freshness=10
    if likes == 0 and days_old <= DISCOVERY_GRADE_PERIOD_DAYS:
        freshness_score = 10.0

    stored_score = quality_score + price_score + demand_score + freshness_score
    live_score = stored_score + proximity_score

    return {
        "live_score": live_score,
        "price_flagged": price_flag,
    }


def _inject_exploration(service_rows: list[dict]) -> None:
    first_flagged = None
    for i, r in enumerate(service_rows):
        if r["price_flagged"]:
            first_flagged = i
            break

    eligible = service_rows[:first_flagged] if first_flagged is not None else service_rows
    if len(eligible) < 2:
        return

    sorted_eligible = sorted(eligible, key=lambda r: -r["live_score"])
    cutoff = max(1, int(len(sorted_eligible) * 0.8))
    pool = sorted_eligible[-(len(sorted_eligible) - cutoff):]
    if not pool:
        return

    pool_indices = list(range(len(eligible)))
    random.shuffle(pool_indices)

    pool_cursor = 0
    for pos in range(EXPLORATION_INTERVAL - 1, len(eligible), EXPLORATION_INTERVAL):
        if pool_cursor >= len(pool_indices):
            break
        source_idx = pool_indices[pool_cursor]
        pool_cursor += 1
        eligible[pos], eligible[source_idx] = eligible[source_idx], eligible[pos]


def calculate_distance_if_possible(
    latitude: Decimal | None,
    longitude: Decimal | None,
    service: ServiceProfile,
) -> float | None:
    if latitude is None or longitude is None:
        return None

    if service.latitude is None or service.longitude is None:
        return None

    return round(
        haversine_km(
            lat1=float(latitude),
            lon1=float(longitude),
            lat2=float(service.latitude),
            lon2=float(service.longitude),
        ),
        2,
    )


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    earth_radius_km = 6371.0

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_km * c


def normalize_city(city_text: str) -> str:
    return " ".join(city_text.strip().lower().split())


def parse_positive_int(value, default: int | None) -> int | None:
    if value is None or value == "":
        return default

    try:
        parsed = int(value)
    except ValueError:
        return default

    if parsed < 1:
        return default

    return parsed


def resolve_discovery_coordinates(telegram_user) -> tuple[Decimal | None, Decimal | None]:
    if telegram_user.has_customer_location:
        return telegram_user.customer_latitude, telegram_user.customer_longitude
    try:
        provider_service = telegram_user.service_profile
        if (provider_service
            and provider_service.approval_status == ServiceProfile.ApprovalStatus.APPROVED
            and provider_service.latitude is not None
            and provider_service.longitude is not None
        ):
            return provider_service.latitude, provider_service.longitude
    except ServiceProfile.DoesNotExist:
        pass
    return None, None


def location_required_response() -> Response:
    return Response(
        {
            "success": False,
            "error": "LOCATION_REQUIRED",
            "message": LOCATION_REQUEST_TEXT,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def linked_user_not_found_response() -> Response:
    return Response(
        {
            "success": False,
            "error": "Authenticated Django user is not linked to a Telegram marketplace user.",
        },
        status=status.HTTP_404_NOT_FOUND,
    )
