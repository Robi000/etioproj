import logging
import math
from decimal import Decimal

from django.utils import timezone

from accounts.models import TelegramUser
from services.models import CityLocation

logger = logging.getLogger("marketplace")

ETHIOPIA_LAT_MIN = Decimal("3.4")
ETHIOPIA_LAT_MAX = Decimal("15.0")
ETHIOPIA_LON_MIN = Decimal("33.0")
ETHIOPIA_LON_MAX = Decimal("48.0")

ADDIS_LAT = 9.03
ADDIS_LON = 38.74
ADDIS_DISTANCE_WARN_KM = 600.0
EARTH_RADIUS_KM = 6371.0

OUTSIDE_ETHIOPIA_TEXT = (
    "Your location seems to be outside Ethiopia. "
    "Please re-share your GPS location from within Ethiopia."
)

LOCATION_REQUEST_TEXT = (
    "To show you nearby service providers, we need your location.\n\n"
    "Please tap the button below to share your GPS location:"
)


def validate_ethiopia_coordinates(lat: Decimal, lon: Decimal) -> tuple[bool, str | None]:
    if lat < ETHIOPIA_LAT_MIN or lat > ETHIOPIA_LAT_MAX:
        return False, OUTSIDE_ETHIOPIA_TEXT
    if lon < ETHIOPIA_LON_MIN or lon > ETHIOPIA_LON_MAX:
        return False, OUTSIDE_ETHIOPIA_TEXT
    return True, None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def is_far_from_addis(lat: float, lon: float) -> bool:
    return haversine_km(lat, lon, ADDIS_LAT, ADDIS_LON) > ADDIS_DISTANCE_WARN_KM


def store_customer_location(user: TelegramUser, lat: Decimal, lon: Decimal) -> None:
    user.customer_latitude = lat
    user.customer_longitude = lon
    user.customer_location_updated_at = timezone.now()

    city_name = CityLocation.get_city_for_coordinates(lon, lat)
    if city_name:
        user.city = city_name

    user.save(update_fields=[
        "customer_latitude", "customer_longitude",
        "customer_location_updated_at", "city", "updated_at",
    ])
