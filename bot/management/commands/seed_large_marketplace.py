from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.defaults import DEFAULT_SERVICE_CATEGORY_NAMES
from services.models import ServiceCategory, ServicePhoto, ServicePrice, ServiceProfile


BASE_TELEGRAM_ID = 880000000
COORD_QUANT = Decimal("0.000001")

CATEGORIES = {
    "Doggy": [
        "Doggy Standard Profile",
        "Doggy Premium Profile",
        "Doggy Nearby Provider",
        "Doggy Evening Provider",
        "Doggy Weekend Provider",
    ],
    "Missionary": [
        "Missionary Standard Profile",
        "Missionary Premium Profile",
        "Missionary Nearby Provider",
        "Missionary Evening Provider",
        "Missionary Weekend Provider",
    ],
    "cowgirl": [
        "cowgirl Standard Profile",
        "cowgirl Premium Profile",
        "cowgirl Nearby Provider",
        "cowgirl Evening Provider",
        "cowgirl Weekend Provider",
    ],
    "Spooning": [
        "Spooning Standard Profile",
        "Spooning Premium Profile",
        "Spooning Nearby Provider",
        "Spooning Evening Provider",
        "Spooning Weekend Provider",
    ],
}

DESCRIPTIONS = {
    category_name: [
        "Demo provider profile with clear availability, friendly communication, and consistent pricing.",
        "Nearby provider profile created for marketplace load testing and discovery flow validation.",
        "Responsive provider profile with reusable photos, badges, and realistic local coordinates.",
    ]
    for category_name in DEFAULT_SERVICE_CATEGORY_NAMES
}

FIRST_NAMES = [
    "Abebe", "Hanna", "Dawit", "Mekdes", "Chala", "Tsion", "Abel", "Hiwot",
    "Yared", "Saba", "Biruk", "Tigist", "Alemu", "Rahel", "Nahom", "Selam",
    "Henok", "Marta", "Bethel", "Kaleb", "Ruth", "Samuel", "Liya", "Yonatan",
    "Eden", "Natnael", "Meron", "Brook", "Lulit", "Fitsum",
]
LAST_NAMES = [
    "Tesfaye", "Bekele", "Alemu", "Tadesse", "Kebede", "Mulugeta", "Gebre",
    "Haile", "Assefa", "Wolde", "Negash", "Desta", "Fikre", "Teshome",
    "Abate", "Demissie", "Girma", "Mengistu", "Getachew", "Solomon",
]

# x is longitude and y is latitude. Most entries are weighted around central Ethiopia.
CITY_CENTERS = [
    ("Addis Ababa", Decimal("38.757800"), Decimal("9.030000"), 52),
    ("Bishoftu", Decimal("38.978500"), Decimal("8.752300"), 10),
    ("Adama", Decimal("39.269500"), Decimal("8.541000"), 10),
    ("Sebeta", Decimal("38.616700"), Decimal("8.916700"), 6),
    ("Holeta", Decimal("38.500000"), Decimal("9.066700"), 5),
    ("Sululta", Decimal("38.750000"), Decimal("9.183300"), 5),
    ("Debre Berhan", Decimal("39.532600"), Decimal("9.679500"), 5),
    ("Hawassa", Decimal("38.476000"), Decimal("7.050000"), 2),
    ("Bahir Dar", Decimal("37.390000"), Decimal("11.600000"), 2),
    ("Dire Dawa", Decimal("41.866100"), Decimal("9.600900"), 1),
    ("Jimma", Decimal("36.833300"), Decimal("7.666700"), 1),
    ("Mekelle", Decimal("39.475300"), Decimal("13.496700"), 1),
]

PRICE_RANGES = {
    "Doggy": {"half_day": (1300, 3500), "full_day": (2600, 6800), "night": (3000, 8200)},
    "Missionary": {"half_day": (1200, 3200), "full_day": (2400, 6500), "night": (2800, 8000)},
    "cowgirl": {"half_day": (1000, 2800), "full_day": (2000, 5600), "night": (2400, 7200)},
    "Spooning": {"half_day": (1100, 3000), "full_day": (2200, 6000), "night": (2600, 7600)},
}


class Command(BaseCommand):
    help = "Seed a large, realistic marketplace dataset for local stress testing."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=200)
        parser.add_argument("--seed", type=int, default=20260630)

    def handle(self, *args, **options):
        count = options["count"]
        if count < 1:
            raise CommandError("--count must be greater than zero.")

        rng = random.Random(options["seed"])
        photo_pool = list(
            ServicePhoto.objects.exclude(telegram_file_id__startswith="http")
            .values_list("telegram_file_id", flat=True)
            .distinct()
        )
        if not photo_pool:
            raise CommandError(
                "No existing Telegram photo IDs found. Add at least one ServicePhoto first."
            )

        categories = self.ensure_categories()
        created_users = 0
        updated_users = 0
        created_services = 0
        updated_services = 0
        created_prices = 0
        created_photos = 0

        self.stdout.write(
            f"Seeding {count} providers with {len(photo_pool)} reusable Telegram photos..."
        )

        with transaction.atomic():
            for index in range(1, count + 1):
                record = self.build_record(index, rng)
                telegram_id = BASE_TELEGRAM_ID + index
                user, user_created = TelegramUser.objects.update_or_create(
                    telegram_id=telegram_id,
                    defaults={
                        "telegram_username": f"demo_provider_{index:03d}",
                        "first_name": record["first_name"],
                        "last_name": record["last_name"],
                        "phone_number": f"+2519{index:08d}"[:13],
                        "secondary_phone_number": f"+2517{index:08d}"[:13],
                        "role": TelegramUser.Role.PROVIDER,
                        "is_verified": record["is_verified"],
                        "admin_tested_badge": record["admin_tested_badge"],
                        "city": record["city"],
                        "likes_count": record["likes_count"],
                        "is_banned": False,
                    },
                )
                if user_created:
                    created_users += 1
                else:
                    updated_users += 1

                auth_user, _ = User.objects.get_or_create(
                    username=f"telegram_{telegram_id}",
                    defaults={
                        "first_name": record["first_name"],
                        "last_name": record["last_name"],
                    },
                )
                Token.objects.get_or_create(user=auth_user)

                service, service_created = ServiceProfile.objects.update_or_create(
                    provider=user,
                    defaults={
                        "category": categories[record["category"]],
                        "title": record["title"],
                        "description": record["description"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                        "city_text": record["city"],
                        "location_source": ServiceProfile.LocationSource.GPS,
                        "visibility_status": ServiceProfile.VisibilityStatus.ON,
                        "approval_status": ServiceProfile.ApprovalStatus.APPROVED,
                        "approved_at": timezone.now() - timedelta(days=rng.randint(1, 90)),
                        "likes_count": record["likes_count"],
                        "admin_forced_hidden": False,
                        "penalty_until": None,
                        "rejection_reason": "",
                    },
                )
                if service_created:
                    created_services += 1
                else:
                    updated_services += 1

                created_at = timezone.now() - timedelta(days=rng.randint(1, 180))
                ServiceProfile.objects.filter(pk=service.pk).update(created_at=created_at)

                service.prices.all().delete()
                for price_type, amount in record["prices"].items():
                    ServicePrice.objects.create(
                        service=service,
                        price_type=price_type,
                        amount=amount,
                    )
                    created_prices += 1

                service.photos.all().delete()
                shuffled_photos = list(photo_pool)
                rng.shuffle(shuffled_photos)
                photo_count = rng.choices([1, 2, 3], weights=[15, 45, 40], k=1)[0]
                for order_index, telegram_file_id in enumerate(shuffled_photos[:photo_count], start=1):
                    ServicePhoto.objects.create(
                        service=service,
                        telegram_file_id=telegram_file_id,
                        order_index=order_index,
                    )
                    created_photos += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"Users created={created_users}, updated={updated_users}; "
                f"services created={created_services}, updated={updated_services}; "
                f"prices created={created_prices}; photos created={created_photos}."
            )
        )

    def ensure_categories(self) -> dict[str, ServiceCategory]:
        categories = {}
        for name in CATEGORIES:
            category, _ = ServiceCategory.objects.update_or_create(
                name=name,
                defaults={"active": True},
            )
            categories[name] = category
        return categories

    def build_record(self, index: int, rng: random.Random) -> dict:
        category = rng.choice(list(CATEGORIES))
        first_name = rng.choice(FIRST_NAMES)
        last_name = rng.choice(LAST_NAMES)
        age = rng.randint(18, 58)
        likes_count = rng.randint(1, 500)
        title_base = rng.choice(CATEGORIES[category])
        city, longitude, latitude = self.random_location(rng)

        description = (
            f"Provider age: {age}. "
            f"{rng.choice(DESCRIPTIONS[category])} "
            f"Based around {city}, with flexible scheduling and clear communication."
        )

        return {
            "first_name": first_name,
            "last_name": last_name,
            "category": category,
            "title": f"Age {age} - {title_base}",
            "description": description,
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "likes_count": likes_count,
            "is_verified": rng.random() < 0.48,
            "admin_tested_badge": rng.random() < 0.32,
            "prices": self.random_prices(category, rng),
        }

    def random_location(self, rng: random.Random) -> tuple[str, Decimal, Decimal]:
        city, center_x, center_y, _weight = rng.choices(
            CITY_CENTERS,
            weights=[item[3] for item in CITY_CENTERS],
            k=1,
        )[0]

        spread = Decimal("0.095") if city in {"Addis Ababa", "Bishoftu", "Adama"} else Decimal("0.045")
        lon = center_x + Decimal(str(rng.uniform(float(-spread), float(spread))))
        lat = center_y + Decimal(str(rng.uniform(float(-spread), float(spread))))

        lat = min(max(lat, Decimal("3.400000")), Decimal("15.000000"))
        lon = min(max(lon, Decimal("33.000000")), Decimal("48.000000"))

        return city, self.quantize(lon), self.quantize(lat)

    def random_prices(self, category: str, rng: random.Random) -> dict[str, Decimal]:
        ranges = PRICE_RANGES[category]
        prices = {
            ServicePrice.PriceType.HALF_DAY: self.random_price(ranges["half_day"], rng),
            ServicePrice.PriceType.FULL_DAY: self.random_price(ranges["full_day"], rng),
        }
        if rng.random() < 0.68:
            prices[ServicePrice.PriceType.NIGHT] = self.random_price(ranges["night"], rng)
        return prices

    def random_price(self, bounds: tuple[int, int], rng: random.Random) -> Decimal:
        value = rng.randrange(bounds[0], bounds[1] + 1, 50)
        return Decimal(value).quantize(Decimal("0.01"))

    def quantize(self, value: Decimal) -> Decimal:
        return value.quantize(COORD_QUANT, rounding=ROUND_HALF_UP)
