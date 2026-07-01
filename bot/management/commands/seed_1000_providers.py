import math
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import TelegramUser
from services.models import ServiceCategory, ServicePhoto, ServicePrice, ServiceProfile

CENTER_LAT = 8.873614
CENTER_LNG = 38.823549

ETHIOPIAN_NAMES = [
    "Abdi", "Abeba", "Abel", "Abenezer", "Abigail", "Abinet", "Adane", "Addis", "Adisu",
    "Afework", "Aklilu", "Akmal", "Alam", "Alehegn", "Alemayehu", "Alemitu", "Alemu",
    "Amanuel", "Amare", "Amsale", "Andualem", "Anteneh", "Aregash", "Arsema", "Aschalew",
    "Asfaw", "Asha", "Ashagre", "Ashenafi", "Askale", "Assefa", "Aster", "Atsede",
    "Awol", "Ayana", "Ayele", "Ayenew", "Bayush", "Behailu", "Behailu", "Bekele",
    "Belay", "Belaynesh", "Berhane", "Berhanu", "Bethelihem", "Beyene", "Biftu", "Birhane",
    "Biruk", "Bisrat", "Bogale", "Bontu", "Bruktawit", "Chala", "Dagne", "Dawit",
    "Degife", "Dejen", "Dereje", "Desalegn", "Desta", "Dinknesh", "Diribe", "Ejigayehu",
    "Eleni", "Elias", "Emebet", "Ephrem", "Ermias", "Eshete", "Eskedar", "Etaferahu",
    "Ezana", "Eyerusalem", "Fana", "Fanuel", "Feleke", "Fikre", "Fikirte", "Frehiwot",
    "Gashaw", "Genet", "Getachew", "Getnet", "Girma", "Gizachew", "Gobeze", "Gutu",
    "Habtamu", "Haddis", "Haftom", "Hagos", "Hailu", "Hana", "Hanna", "Henok",
    "Heran", "Hewan", "Hiwot", "Hundessa", "Huruy", "Insaf", "Issayas", "Jemila",
    "Jemal", "Kaleb", "Kaleyesus", "Kalkidan", "Kassahun", "Kebede", "Kebedech",
    "Kemer", "Kidist", "Kidusan", "Kifle", "Kiya", "Kokeb", "Konjit", "Kumneger",
    "Lamesgin", "Lemlem", "Leteberhan", "Lidetu", "Liya", "Lulit", "Luwam", "Maaza",
    "Makeda", "Mamo", "Martha", "Mastewal", "Mathewos", "Mebratu", "Medhin", "Mehret",
    "Mekdes", "Mekonnen", "Mekuria", "Melaku", "Mela", "Melekte", "Melese", "Meles",
    "Meron", "Meseret", "Mesfin", "Meskerm", "Michele", "Mihret", "Miki", "Mintesnot",
    "Mirtse", "Misrak", "Moges", "Mohammed", "Mulatu", "Mulgeta", "Mulu", "Mulugeta",
    "Mulunesh", "Mussie", "Muluwork", "Naod", "Nardos", "Nasise", "Negash", "Negussie",
    "Netsanet", "Nibret", "Nigist", "Nuredin", "Rahwa", "Rediet", "Rehima", "Robel",
    "Ruth", "Saba", "Saba", "Sahle", "Sahlu", "Said", "Salam", "Samrawit", "Samuel",
    "Sara", "Selam", "Selamawit", "Selassie", "Senait", "Senay", "Serawit", "Shambel",
    "Shemsu", "Shiferaw", "Shimelis", "Sisay", "Solomon", "Sosina", "Surafel", "Tabitu",
    "Tadele", "Tadesse", "Tafesse", "Tagesu", "Takele", "Tamrat", "Tarik", "Tasew",
    "Tayitu", "Taye", "Tedla", "Tekeste", "Tekle", "Teklu", "Temesgen", "Tesfaye",
    "Teshome", "Tigist", "Tigistu", "Tilahun", "Timket", "Tirsit", "Tsega", "Tsegaye",
    "Tsehai", "Tsehay", "Tsehaynesh", "Tsige", "Tsion", "Ubah", "Wagaye", "Wasse",
    "Webshe", "Winta", "Wondimu", "Wondwosen", "Worke", "Worknesh", "Wossen", "Yabsira",
    "Yalem", "Yalemwork", "Yared", "Yaye", "Yeabsira", "Yemane", "Yemisrach", "Yene",
    "Yeneneh", "Yerga", "Yeshi", "Yeshitila", "Yetnebersh", "Yohannes", "Yonas",
    "Yordanos", "Yosef", "Zaid", "Zala", "Zebene", "Zekarias", "Zelalem", "Zena",
    "Zerai", "Zerihun", "Zewdie", "Zufan", "Zufan",
]

TITLES = [
    "Relaxing {cat} Experience", "Premium {cat} Service", "Luxury {cat} Session",
    "Intimate {cat} Moments", "Sensual {cat} Adventure", "Passionate {cat} Encounter",
    "Blissful {cat} Retreat", "Ultimate {cat} Pleasure", "Exclusive {cat} Treat",
    "Divine {cat} Connection", "Heavenly {cat} Escape", "Irresistible {cat} Charm",
    "Perfect {cat} Getaway", "Romantic {cat} Journey", "Enchanting {cat} Night",
    "Dreamy {cat} Session", "Tender {cat} Moments", "Sizzling {cat} Affair",
    "Elegant {cat} Date", "Sensational {cat} Experience",
]

DESCRIPTIONS = [
    "Experience the ultimate relaxation and connection. I provide a warm, safe, and unforgettable experience tailored just for you.",
    "Let me take you on a journey of pleasure and comfort. Every session is unique and designed to make you feel special.",
    "Indulge in a premium experience with attention to every detail. Your satisfaction and comfort are my top priorities.",
    "Discover true intimacy in a welcoming environment. I am here to make your experience memorable and fulfilling.",
    "Unwind and enjoy a luxurious session filled with passion and care. Every moment is crafted for your pleasure.",
    "Treat yourself to an extraordinary experience. Professional, discreet, and dedicated to your complete satisfaction.",
    "Escape the ordinary with a session that combines elegance, passion, and genuine connection. You deserve the best.",
    "Welcome to a world of sensuality and warmth. I pride myself on creating a comfortable and exciting atmosphere.",
    "Your pleasure is my mission. Let me guide you through an experience that will leave you wanting more.",
    "Step into a haven of relaxation and desire. Every session is a new adventure waiting to be explored.",
]

CATEGORY_NAMES = ["Doggy", "Missionary", "cowgirl", "Spooning"]
PHOTO_URLS = [
    "https://picsum.photos/seed/service1/400/300",
    "https://picsum.photos/seed/service2/400/300",
    "https://picsum.photos/seed/service3/400/300",
]


def gps_offset(lat, lng, radius_km=5.0):
    lat_change = radius_km / 111.0
    lng_change = radius_km / (111.0 * abs(math.cos(math.radians(lat))) or 1)
    return (
        round(lat + random.uniform(-lat_change, lat_change), 6),
        round(lng + random.uniform(-lng_change, lng_change), 6),
    )


class Command(BaseCommand):
    help = "Seed ~1000 providers near Addis Ababa with existing categories and photos"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=1000, help="Number of providers to create")
        parser.add_argument("--start-tg-id", type=int, default=8000000, help="Starting telegram_id")

    def handle(self, *args, **options):
        total = options["count"]
        start_tg = options["start_tg_id"]

        for name in CATEGORY_NAMES:
            ServiceCategory.objects.get_or_create(name=name, defaults={"active": True})
        cat_map = {c.name: c for c in ServiceCategory.objects.all()}

        existing = TelegramUser.objects.filter(telegram_id__gte=start_tg).count()
        self.stdout.write(f"Existing users with tg_id >= {start_tg}: {existing}")
        if existing >= total:
            self.stdout.write(self.style.WARNING(f"Already have {existing} users — skipping"))
            return

        created = 0
        batch = []
        tg_id = start_tg
        start_time = timezone.now()

        self.stdout.write(f"Seeding {total} providers near ({CENTER_LAT}, {CENTER_LNG})...")

        while created < total:
            tg_id += 1
            name = random.choice(ETHIOPIAN_NAMES)
            username = f"{name.lower()}_{tg_id}"[:30]
            phone = f"+2519{random.randint(10000000, 99999999)}"

            is_verified = random.random() < 0.4
            is_tested = random.random() < 0.25 and is_verified

            user = TelegramUser(
                telegram_id=tg_id,
                telegram_username=username,
                first_name=name,
                phone_number=phone,
                role=TelegramUser.Role.PROVIDER,
                is_verified=is_verified,
                is_banned=False,
                admin_tested_badge=is_tested,
                policy_accepted_at=start_time,
                policy_version="1.0",
            )

            lat, lng = gps_offset(CENTER_LAT, CENTER_LNG)
            category = random.choice(list(cat_map.values()))
            title = random.choice(TITLES).format(cat=category.name)
            days_old = random.randint(1, 180)

            service = ServiceProfile(
                provider=user,
                category=category,
                title=title,
                description=random.choice(DESCRIPTIONS),
                city_text="Addis Ababa",
                latitude=lat,
                longitude=lng,
                location_source=ServiceProfile.LocationSource.GPS,
                visibility_status=ServiceProfile.VisibilityStatus.ON,
                approval_status=ServiceProfile.ApprovalStatus.APPROVED,
                likes_count=random.randint(0, 50),
            )

            batch.append((user, service))

            if len(batch) >= 100 or created + len(batch) >= total:
                TelegramUser.objects.bulk_create([u for u, _ in batch], ignore_conflicts=True)

                re_users = {u.telegram_id: u for u in TelegramUser.objects.filter(
                    telegram_id__in=[u.telegram_id for u, _ in batch]
                )}

                services_to_create = []
                for u, svc in batch:
                    db_user = re_users.get(u.telegram_id)
                    if not db_user:
                        continue
                    svc.provider = db_user
                    services_to_create.append(svc)

                if services_to_create:
                    ServiceProfile.objects.bulk_create(services_to_create, ignore_conflicts=True)

                created += len(batch)
                self.stdout.write(f"  Created {created}/{total}...")
                batch = []

        self.stdout.write(f"\nAll {created} TelegramUsers created.")
        self.stdout.write("Creating prices and photos...")

        profiles = ServiceProfile.objects.filter(
            provider__telegram_id__gte=start_tg,
            provider__telegram_id__lte=tg_id,
        ).select_related("provider").order_by("id")

        price_entries = []
        photo_entries = []
        price_count = 0
        photo_count = 0

        for svc in profiles:
            num_prices = random.randint(1, 3)
            types = random.sample(["half_day", "full_day", "night"], k=num_prices)
            for pt in types:
                amount = round(random.uniform(800, 5000), -2)
                price_entries.append(
                    ServicePrice(service=svc, price_type=pt, amount=amount)
                )
            price_count += num_prices

            num_photos = random.randint(2, 3)
            indices = random.sample([1, 2, 3], k=num_photos)
            for idx in indices:
                photo_entries.append(
                    ServicePhoto(
                        service=svc,
                        telegram_file_id=PHOTO_URLS[idx - 1],
                        order_index=idx,
                    )
                )
            photo_count += num_photos

            if svc.created_at is None:
                ServiceProfile.objects.filter(pk=svc.pk).update(
                    created_at=start_time - timedelta(days=random.randint(1, 180))
                )

            if len(price_entries) >= 500:
                ServicePrice.objects.bulk_create(price_entries, ignore_conflicts=True)
                price_entries = []
            if len(photo_entries) >= 500:
                ServicePhoto.objects.bulk_create(photo_entries, ignore_conflicts=True)
                photo_entries = []

        if price_entries:
            ServicePrice.objects.bulk_create(price_entries, ignore_conflicts=True)
        if photo_entries:
            ServicePhoto.objects.bulk_create(photo_entries, ignore_conflicts=True)

        elapsed = (timezone.now() - start_time).total_seconds()
        self.stdout.write(self.style.SUCCESS(
            f"\nDone in {elapsed:.1f}s: {created} providers, {price_count} prices, "
            f"{photo_count} photos\n"
            f"Badge distribution: verified+tested={sum(1 for s in profiles if s.provider.admin_tested_badge)}, "
            f"verified only={sum(1 for s in profiles if s.provider.is_verified and not s.provider.admin_tested_badge)}, "
            f"neither={sum(1 for s in profiles if not s.provider.is_verified)}"
        ))
