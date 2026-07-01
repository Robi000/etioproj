from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import TelegramUser
from services.models import (
    ServiceCategory,
    ServicePhoto,
    ServicePrice,
    ServiceProfile,
)

DEMO_SERVICES = [
    {
        "provider_tg_id": 90001,
        "provider_username": "hanna_plumber",
        "provider_name": "Hanna",
        "phone": "+251911100001",
        "role": TelegramUser.Role.PROVIDER,
        "is_verified": True,
        "title": "Pipe Repair & Installation",
        "description": "Professional pipe repair, installation, and maintenance for residential and commercial properties. Fast response, quality work.",
        "category_name": "Doggy",
        "city_text": "Addis Ababa",
        "latitude": "9.030000",
        "longitude": "38.750000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "1500.00"),
            ("full_day", "2500.00"),
            ("night", "3000.00"),
        ],
        "likes_count": 12,
        "days_old": 30,
    },
    {
        "provider_tg_id": 90011,
        "provider_username": "chala_plumber",
        "provider_name": "Chala",
        "phone": "+251911100011",
        "role": TelegramUser.Role.PROVIDER,
        "title": "Emergency Plumbing Services",
        "description": "24/7 emergency plumbing services. Burst pipes, leaks, blocked drains. Available on weekends and holidays.",
        "category_name": "Doggy",
        "city_text": "Addis Ababa",
        "latitude": "9.020000",
        "longitude": "38.730000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "2000.00"),
            ("full_day", "3500.00"),
        ],
        "likes_count": 8,
        "days_old": 15,
    },
    {
        "provider_tg_id": 90002,
        "provider_username": "dawit_electric",
        "provider_name": "Dawit",
        "phone": "+251911100002",
        "role": TelegramUser.Role.PROVIDER,
        "is_verified": True,
        "title": "Electrical Wiring & Rewiring",
        "description": "Complete electrical wiring services for new construction and renovations. Certified electrician with 10+ years experience.",
        "category_name": "Missionary",
        "city_text": "Addis Ababa",
        "latitude": "9.035000",
        "longitude": "38.760000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "1800.00"),
            ("full_day", "3000.00"),
            ("night", "3500.00"),
        ],
        "likes_count": 25,
        "days_old": 45,
    },
    {
        "provider_tg_id": 90003,
        "provider_username": "mekdes_tutor",
        "provider_name": "Mekdes",
        "phone": "+251911100003",
        "role": TelegramUser.Role.BOTH,
        "title": "Math Tutoring (Grade 1-12)",
        "description": "Experienced math tutor for all grade levels. Specializing in exam preparation, homework help, and concept building.",
        "category_name": "cowgirl",
        "city_text": "Addis Ababa",
        "latitude": "9.010000",
        "longitude": "38.720000",
        "location_source": ServiceProfile.LocationSource.BOTH,
        "prices": [
            ("half_day", "800.00"),
            ("full_day", "1500.00"),
        ],
        "likes_count": 6,
        "days_old": 20,
    },
    {
        "provider_tg_id": 90012,
        "provider_username": "tsion_tutor",
        "provider_name": "Tsion",
        "phone": "+251911100012",
        "role": TelegramUser.Role.PROVIDER,
        "title": "English Language Coaching",
        "description": "Conversational English, business English, and academic writing coaching. Customized lessons for all skill levels.",
        "category_name": "cowgirl",
        "city_text": "Addis Ababa",
        "latitude": "9.015000",
        "longitude": "38.725000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "1000.00"),
            ("full_day", "1800.00"),
            ("night", "2000.00"),
        ],
        "likes_count": 15,
        "days_old": 10,
    },
    {
        "provider_tg_id": 90004,
        "provider_username": "abebe_mechanic",
        "provider_name": "Abebe",
        "phone": "+251911100004",
        "role": TelegramUser.Role.PROVIDER,
        "title": "Car Repair & Maintenance",
        "description": "Full-service auto repair shop. Engine diagnostics, brake repair, oil changes, tire rotation, and more. Quality parts guaranteed.",
        "category_name": "Spooning",
        "city_text": "Adama",
        "latitude": "8.540000",
        "longitude": "39.270000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "2500.00"),
            ("full_day", "4500.00"),
        ],
        "likes_count": 20,
        "days_old": 60,
    },
    {
        "provider_tg_id": 90005,
        "provider_username": "tigist_clean",
        "provider_name": "Tigist",
        "phone": "+251911100005",
        "role": TelegramUser.Role.PROVIDER,
        "is_verified": True,
        "title": "Home & Office Cleaning",
        "description": "Deep cleaning services for homes and offices. Eco-friendly products, trained staff, affordable rates. Weekly or monthly plans available.",
        "category_name": "Doggy",
        "city_text": "Addis Ababa",
        "latitude": "9.025000",
        "longitude": "38.745000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "1200.00"),
            ("full_day", "2000.00"),
            ("night", "2500.00"),
        ],
        "likes_count": 30,
        "days_old": 25,
    },
    {
        "provider_tg_id": 90006,
        "provider_username": "biruk_allround",
        "provider_name": "Biruk",
        "phone": "+251911100006",
        "role": TelegramUser.Role.BOTH,
        "title": "Quality Painting Service",
        "description": "Interior and exterior painting for homes and businesses. Professional finish, premium paints, free color consultation.",
        "category_name": "Doggy",
        "city_text": "Hawassa",
        "latitude": "7.050000",
        "longitude": "38.480000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "1800.00"),
            ("full_day", "3200.00"),
        ],
        "likes_count": 5,
        "days_old": 5,
    },
    {
        "provider_tg_id": 90013,
        "provider_username": "abel_furniture",
        "provider_name": "Abel",
        "phone": "+251911100013",
        "role": TelegramUser.Role.PROVIDER,
        "title": "Furniture Assembly Service",
        "description": "Professional furniture assembly for IKEA and other flat-pack furniture. Fast, reliable, and careful with your items.",
        "category_name": "Spooning",
        "city_text": "Hawassa",
        "latitude": "7.055000",
        "longitude": "38.485000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "900.00"),
            ("full_day", "1600.00"),
        ],
        "likes_count": 3,
        "days_old": 2,
    },
    {
        "provider_tg_id": 90007,
        "provider_username": "saba_tutor",
        "provider_name": "Saba",
        "phone": "+251911100007",
        "role": TelegramUser.Role.PROVIDER,
        "title": "Computer Programming Lessons",
        "description": "Learn Python, JavaScript, or web development. Beginner to advanced. Project-based learning with real-world examples.",
        "category_name": "cowgirl",
        "city_text": "Mekele",
        "latitude": "13.500000",
        "longitude": "39.470000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "2500.00"),
            ("full_day", "4000.00"),
            ("night", "3500.00"),
        ],
        "likes_count": 18,
        "days_old": 35,
    },
    {
        "provider_tg_id": 90008,
        "provider_username": "alemu_plumber",
        "provider_name": "Alemu",
        "phone": "+251911100008",
        "role": TelegramUser.Role.PROVIDER,
        "title": "Bathroom Renovation",
        "description": "Complete bathroom renovation including tiling, fixtures, plumbing, and painting. Transform your bathroom with quality workmanship.",
        "category_name": "Doggy",
        "city_text": "Addis Ababa",
        "latitude": "9.040000",
        "longitude": "38.770000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("full_day", "5000.00"),
            ("night", "6000.00"),
        ],
        "likes_count": 10,
        "days_old": 40,
    },
    {
        "provider_tg_id": 90009,
        "provider_username": "hiwot_electric",
        "provider_name": "Hiwot",
        "phone": "+251911100009",
        "role": TelegramUser.Role.PROVIDER,
        "title": "Solar Panel Installation",
        "description": "Affordable solar energy solutions for homes and businesses. Installation, maintenance, and repair of solar systems.",
        "category_name": "Missionary",
        "city_text": "Adama",
        "latitude": "8.545000",
        "longitude": "39.275000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "3000.00"),
            ("full_day", "5500.00"),
        ],
        "likes_count": 22,
        "days_old": 50,
    },
    {
        "provider_tg_id": 90010,
        "provider_username": "yared_clean",
        "provider_name": "Yared",
        "phone": "+251911100010",
        "role": TelegramUser.Role.PROVIDER,
        "title": "Carpet & Upholstery Cleaning",
        "description": "Professional carpet and upholstery cleaning using steam extraction. Removes stains, allergens, and odors effectively.",
        "category_name": "Doggy",
        "city_text": "Addis Ababa",
        "latitude": "9.008000",
        "longitude": "38.735000",
        "location_source": ServiceProfile.LocationSource.GPS,
        "prices": [
            ("half_day", "1500.00"),
            ("full_day", "2800.00"),
        ],
        "likes_count": 7,
        "days_old": 8,
    },
]

PHOTO_URLS = [
    "https://picsum.photos/seed/service1/400/300",
    "https://picsum.photos/seed/service2/400/300",
    "https://picsum.photos/seed/service3/400/300",
]


class Command(BaseCommand):
    help = "Seed 10+ demo services across providers, categories, and cities"

    CATEGORY_NAMES = ["Doggy", "Missionary", "cowgirl", "Spooning"]

    def handle(self, *args, **options):
        self.stdout.write("Seeding demo services...\n")

        for name in self.CATEGORY_NAMES:
            ServiceCategory.objects.get_or_create(name=name, defaults={"active": True})
        cat_map = {c.name: c for c in ServiceCategory.objects.all()}

        created_providers = 0
        created_services = 0
        created_prices = 0
        created_photos = 0
        skipped = 0

        for svc_data in DEMO_SERVICES:
            tg_id = svc_data["provider_tg_id"]
            user, was_created = TelegramUser.objects.get_or_create(
                telegram_id=tg_id,
                defaults={
                    "first_name": svc_data["provider_name"],
                    "role": svc_data["role"],
                    "phone_number": svc_data["phone"],
                    "telegram_username": svc_data["provider_username"],
                    "is_verified": svc_data.get("is_verified", False),
                    "admin_tested_badge": svc_data.get("is_verified", False),
                },
            )
            if was_created:
                created_providers += 1
                django_user = User.objects.create_user(
                    username=f"telegram_{tg_id}",
                )
                Token.objects.create(user=django_user)
                self.stdout.write(f"  Created provider: {svc_data['provider_name']} (tg={tg_id})")
            else:
                self.stdout.write(f"  Using existing provider: {user.first_name or svc_data['provider_name']} (tg={tg_id})")

            category = cat_map.get(svc_data["category_name"])
            if not category:
                self.stdout.write(f"  [SKIP] Category '{svc_data['category_name']}' not found")
                skipped += 1
                continue

            svc, svc_created = ServiceProfile.objects.get_or_create(
                provider=user,
                defaults={
                    "category": category,
                    "title": svc_data["title"],
                    "description": svc_data["description"],
                    "city_text": svc_data["city_text"],
                    "latitude": svc_data["latitude"],
                    "longitude": svc_data["longitude"],
                    "location_source": svc_data["location_source"],
                    "likes_count": svc_data["likes_count"],
                    "approval_status": ServiceProfile.ApprovalStatus.APPROVED,
                    "visibility_status": ServiceProfile.VisibilityStatus.ON,
                },
            )
            if svc_created:
                created_services += 1

                if svc_data["days_old"]:
                    ServiceProfile.objects.filter(pk=svc.pk).update(
                        created_at=timezone.now() - timedelta(days=svc_data["days_old"])
                    )
                    svc.refresh_from_db()

                for price_type, amount in svc_data["prices"]:
                    ServicePrice.objects.create(
                        service=svc,
                        price_type=price_type,
                        amount=amount,
                    )
                    created_prices += 1

                for idx, url in enumerate(PHOTO_URLS, start=1):
                    sp = ServicePhoto.objects.create(
                        service=svc,
                        telegram_file_id=url,
                        order_index=idx,
                    )
                    from services.photo_storage import store_photo_locally
                    store_photo_locally(sp)
                    created_photos += 1

                self.stdout.write(f"  Created service: [{svc.id}] {svc.title}")
            else:
                self.stdout.write(f"  [SKIP] Service already exists: {svc.title}")
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created {created_providers} providers, {created_services} services, "
            f"{created_prices} prices, {created_photos} photos. Skipped {skipped}."
        ))
