from django.db import migrations


DEFAULT_SERVICE_CATEGORY_NAMES = (
    "Doggy",
    "Missionary",
    "cowgirl",
    "Spooning",
)

OLD_DEFAULT_SERVICE_CATEGORY_NAMES = (
    "Electrician",
    "Cleaner",
    "Tutor",
    "Mechanic",
    "Plumber",
)


def apply_default_categories(apps, schema_editor):
    service_category = apps.get_model("services", "ServiceCategory")

    for name in DEFAULT_SERVICE_CATEGORY_NAMES:
        service_category.objects.update_or_create(
            name=name,
            defaults={"active": True},
        )

    service_category.objects.filter(
        name__in=OLD_DEFAULT_SERVICE_CATEGORY_NAMES,
    ).update(active=False)


def restore_old_default_categories(apps, schema_editor):
    service_category = apps.get_model("services", "ServiceCategory")

    service_category.objects.filter(
        name__in=DEFAULT_SERVICE_CATEGORY_NAMES,
    ).update(active=False)

    for name in OLD_DEFAULT_SERVICE_CATEGORY_NAMES:
        service_category.objects.update_or_create(
            name=name,
            defaults={"active": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0009_seed_city_locations"),
    ]

    operations = [
        migrations.RunPython(
            apply_default_categories,
            restore_old_default_categories,
        ),
    ]
