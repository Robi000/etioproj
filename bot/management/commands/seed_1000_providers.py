from __future__ import annotations

import os
import random
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServicePhoto, ServicePrice, ServiceProfile


BASE_TELEGRAM_ID = 990000000
COORD_QUANT = Decimal("0.000001")

ETHIOPIAN_FIRST_NAMES = [
    "Abebe", "Hanna", "Dawit", "Mekdes", "Chala", "Tsion", "Abel", "Hiwot",
    "Yared", "Saba", "Biruk", "Tigist", "Alemu", "Rahel", "Nahom", "Selam",
    "Henok", "Marta", "Bethel", "Kaleb", "Ruth", "Samuel", "Liya", "Yonatan",
    "Eden", "Natnael", "Meron", "Brook", "Lulit", "Fitsum", "Birtukan",
    "Mahlet", "Kidist", "Tekle", "Yonas", "Biniyam", "Ephrem", "Surafel",
    "Mastewal", "Tsehay", "Worknesh", "Mulu", "Aster", "Gebre", "Tadesse",
]

ETHIOPIAN_LAST_NAMES = [
    "Tesfaye", "Bekele", "Alemu", "Tadesse", "Kebede", "Mulugeta", "Gebre",
    "Haile", "Assefa", "Wolde", "Negash", "Desta", "Fikre", "Teshome",
    "Abate", "Demissie", "Girma", "Mengistu", "Getachew", "Solomon",
    "Berhanu", "Defar", "Eshetu", "Fekadu", "Wondimu", "Zenebe",
]

CATEGORY_TITLES = {
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
    cat: [
        "Friendly provider with clear availability and consistent pricing.",
        "Nearby provider with flexible scheduling and great communication.",
        "Responsive provider with quality service and fair rates.",
        "Experienced provider focused on customer satisfaction.",
        "Reliable provider with prompt service and positive reviews.",
    ]
    for cat in ["Doggy", "Missionary", "cowgirl", "Spooning"]
}

PRICE_RANGES = {
    "Doggy": {"half_day": (1300, 3500), "full_day": (2600, 6800), "night": (3000, 8200)},
    "Missionary": {"half_day": (1200, 3200), "full_day": (2400, 6500), "night": (2800, 8000)},
    "cowgirl": {"half_day": (1000, 2800), "full_day": (2000, 5600), "night": (2400, 7200)},
    "Spooning": {"half_day": (1100, 3000), "full_day": (2200, 6000), "night": (2600, 7600)},
}

# Bounding box for the 4 given coordinates
# lat: 8.839019 to 9.128243
# lon: 38.552644 to 38.893267
LAT_MIN = Decimal("8.839019")
LAT_MAX = Decimal("9.128243")
LON_MIN = Decimal("38.552644")
LON_MAX = Decimal("38.893267")


class Command(BaseCommand):
    help = "Seed 1000 service providers within a custom GPS bounding box"

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=20260704)

    def handle(self, *args, **options):
        rng = random.Random(options["seed"])

        # Load existing local photos from disk
        photo_paths = self._get_local_photo_paths()
        if not photo_paths:
            raise CommandError(
                "No existing photo files found in media/service_photos/. "
                "Run seed_demo_services first or add photos manually."
            )
        self.stdout.write(f"Found {len(photo_paths)} local photo files.\n")

        categories = self._ensure_categories()
        existing_users = TelegramUser.objects.count()

        created_users = 0
        created_services = 0
        created_prices = 0
        created_photos = 0
        skipped = 0

        self.stdout.write("Seeding 1000 providers...\n")

        with transaction.atomic():
            for index in range(1, 1001):
                telegram_id = BASE_TELEGRAM_ID + index
                age = rng.randint(18, 40)
                category_name = rng.choice(list(CATEGORY_TITLES))
                first_name = rng.choice(ETHIOPIAN_FIRST_NAMES)
                last_name = rng.choice(ETHIOPIAN_LAST_NAMES)

                latitude = self._random_lat(rng)
                longitude = self._random_lon(rng)

                service_title = str(age)

                likes_count = rng.randint(0, 300)
                is_verified = rng.random() < 0.40
                admin_tested = rng.random() < 0.25

                username = f"seed_provider_{index:04d}"
                phone = f"+2519{rng.randint(10000000, 99999999)}"
                secondary = f"+2517{rng.randint(10000000, 99999999)}"

                days_old = rng.randint(1, 120)
                created_at = timezone.now() - timedelta(days=days_old)

                description = (
                    f"Provider age: {age}. "
                    f"{rng.choice(DESCRIPTIONS[category_name])} "
                    f"Available in Addis Ababa area."
                )

                user, user_created = TelegramUser.objects.get_or_create(
                    telegram_id=telegram_id,
                    defaults={
                        "telegram_username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                        "phone_number": phone,
                        "secondary_phone_number": secondary,
                        "role": TelegramUser.Role.PROVIDER,
                        "is_verified": is_verified,
                        "admin_tested_badge": admin_tested,
                        "city": "Addis Ababa",
                        "likes_count": likes_count,
                        "is_banned": False,
                    },
                )

                if user_created:
                    created_users += 1
                    auth_user, _ = User.objects.get_or_create(
                        username=f"telegram_{telegram_id}",
                    )
                    Token.objects.get_or_create(user=auth_user)
                else:
                    skipped += 1
                    continue

                service, service_created = ServiceProfile.objects.get_or_create(
                    provider=user,
                    defaults={
                        "category": categories[category_name],
                        "title": service_title,
                        "description": description,
                        "latitude": latitude,
                        "longitude": longitude,
                        "city_text": "Addis Ababa",
                        "location_source": ServiceProfile.LocationSource.GPS,
                        "visibility_status": ServiceProfile.VisibilityStatus.ON,
                        "approval_status": ServiceProfile.ApprovalStatus.APPROVED,
                        "approved_at": timezone.now() - timedelta(days=rng.randint(1, 90)),
                        "likes_count": likes_count,
                        "admin_forced_hidden": False,
                        "penalty_until": None,
                        "rejection_reason": "",
                    },
                )

                if service_created:
                    ServiceProfile.objects.filter(pk=service.pk).update(created_at=created_at)
                    created_services += 1
                else:
                    skipped += 1
                    continue

                # Prices
                price_ranges = PRICE_RANGES[category_name]
                prices_data = {
                    ServicePrice.PriceType.HALF_DAY: self._random_price(price_ranges["half_day"], rng),
                    ServicePrice.PriceType.FULL_DAY: self._random_price(price_ranges["full_day"], rng),
                }
                if rng.random() < 0.60:
                    prices_data[ServicePrice.PriceType.NIGHT] = self._random_price(price_ranges["night"], rng)

                for price_type, amount in prices_data.items():
                    ServicePrice.objects.create(
                        service=service,
                        price_type=price_type,
                        amount=amount,
                    )
                    created_prices += 1

                # Photos — pick 1-3 random local photos and copy them
                photo_count = rng.choices([1, 2, 3], weights=[15, 45, 40], k=1)[0]
                chosen_paths = rng.sample(photo_paths, min(photo_count, len(photo_paths)))
                for order_index, file_path in enumerate(chosen_paths, start=1):
                    with open(file_path, "rb") as f:
                        content = f.read()
                    file_name = os.path.basename(file_path)
                    sp = ServicePhoto(
                        service=service,
                        telegram_file_id=file_name,
                        order_index=order_index,
                    )
                    sp.image.save(
                        f"seed_{telegram_id}_{order_index}_{file_name}",
                        ContentFile(content),
                        save=False,
                    )
                    sp.full_clean()
                    sp.save()
                    created_photos += 1

                if index % 100 == 0:
                    self.stdout.write(f"  {index}/1000 providers seeded...")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. "
                f"Users created: {created_users}, "
                f"services created: {created_services}, "
                f"prices created: {created_prices}, "
                f"photos created: {created_photos}, "
                f"skipped: {skipped}."
                f"\nTotal TelegramUsers now: {TelegramUser.objects.count()} "
                f"(was {existing_users})."
            )
        )

    def _get_local_photo_paths(self) -> list[str]:
        media_dir = os.path.join(settings.MEDIA_ROOT, "service_photos")
        if not os.path.isdir(media_dir):
            return []
        paths = []
        for fname in sorted(os.listdir(media_dir)):
            full = os.path.join(media_dir, fname)
            if os.path.isfile(full) and fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                paths.append(full)
        return paths

    def _ensure_categories(self) -> dict[str, ServiceCategory]:
        categories = {}
        for name in CATEGORY_TITLES:
            cat, _ = ServiceCategory.objects.update_or_create(
                name=name,
                defaults={"active": True},
            )
            categories[name] = cat
        return categories

    def _random_lat(self, rng: random.Random) -> Decimal:
        raw = rng.uniform(float(LAT_MIN), float(LAT_MAX))
        return Decimal(raw).quantize(COORD_QUANT, rounding=ROUND_HALF_UP)

    def _random_lon(self, rng: random.Random) -> Decimal:
        raw = rng.uniform(float(LON_MIN), float(LON_MAX))
        return Decimal(raw).quantize(COORD_QUANT, rounding=ROUND_HALF_UP)

    def _random_price(self, bounds: tuple[int, int], rng: random.Random) -> Decimal:
        value = rng.randrange(bounds[0], bounds[1] + 1, 50)
        return Decimal(value).quantize(Decimal("0.01"))
