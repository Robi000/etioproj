from django.db import migrations


CITIES = [
    {
        "name": "Addis Ababa",
        "top_left_x": "38.623104", "top_left_y": "9.123600",
        "top_right_x": "38.939476", "top_right_y": "9.123600",
        "bottom_right_x": "38.939476", "bottom_right_y": "8.850684",
        "bottom_left_x": "38.623104", "bottom_left_y": "8.850684",
    },
    {
        "name": "Adama",
        "top_left_x": "39.207899", "top_left_y": "8.597673",
        "top_right_x": "39.326241", "top_right_y": "8.597673",
        "bottom_right_x": "39.326241", "bottom_right_y": "8.461662",
        "bottom_left_x": "39.207899", "bottom_left_y": "8.461662",
    },
    {
        "name": "Hawassa",
        "top_left_x": "38.444053", "top_left_y": "7.113437",
        "top_right_x": "38.536641", "top_right_y": "7.113437",
        "bottom_right_x": "38.536641", "bottom_right_y": "7.003403",
        "bottom_left_x": "38.444053", "bottom_left_y": "7.003403",
    },
    {
        "name": "Mekele",
        "top_left_x": "39.423693", "top_left_y": "13.582725",
        "top_right_x": "39.523714", "top_right_y": "13.582725",
        "bottom_right_x": "39.523714", "bottom_right_y": "13.457733",
        "bottom_left_x": "39.423693", "bottom_left_y": "13.457733",
    },
]


def seed_cities(apps, schema_editor):
    CityLocation = apps.get_model("services", "CityLocation")
    for city_data in CITIES:
        defaults = {k: v for k, v in city_data.items() if k != "name"}
        CityLocation.objects.update_or_create(
            name=city_data["name"],
            defaults=defaults,
        )


def clear_cities(apps, schema_editor):
    CityLocation = apps.get_model("services", "CityLocation")
    CityLocation.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0008_serviceprofile_prior_penalty_count'),
    ]

    operations = [
        migrations.RunPython(seed_cities, clear_cities),
    ]
