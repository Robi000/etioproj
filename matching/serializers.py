from rest_framework import serializers

from services.models import ServiceProfile


class DiscoveryPriceSerializer(serializers.Serializer):
    price_type = serializers.CharField()
    amount = serializers.CharField()


class DiscoveryPhotoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    telegram_file_id = serializers.CharField()
    order_index = serializers.IntegerField()


class DiscoveryServiceCardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    category = serializers.DictField()
    city_text = serializers.CharField(allow_blank=True, allow_null=True)
    distance_km = serializers.FloatField(allow_null=True)
    prices = DiscoveryPriceSerializer(many=True)
    photos = DiscoveryPhotoSerializer(many=True)
    visibility_status = serializers.CharField()
    approval_status = serializers.CharField()
    provider_name = serializers.CharField()
    is_verified = serializers.BooleanField()
    admin_tested_badge = serializers.BooleanField()
    provider_is_verified = serializers.BooleanField()
    provider_admin_tested_badge = serializers.BooleanField()
    likes_count = serializers.IntegerField()
    is_own = serializers.BooleanField()


def build_discovery_card(
    service: ServiceProfile,
    distance_km: float | None,
    is_own: bool = False,
) -> dict:
    provider = service.provider
    return {
        "id": service.id,
        "title": service.title,
        "description": service.description,
        "category": {
            "id": service.category_id,
            "name": service.category.name,
        },
        "city_text": service.city_text,
        "distance_km": distance_km,
        "prices": [
            {
                "price_type": price.price_type,
                "amount": str(price.amount),
            }
            for price in service.prices.all()
        ],
        "photos": [
            {
                "id": photo.id,
                "telegram_file_id": photo.telegram_file_id,
                "order_index": photo.order_index,
            }
            for photo in service.photos.all()
        ],
        "visibility_status": service.visibility_status,
        "approval_status": service.approval_status,
        "provider_name": provider.get_display_name(),
        "is_verified": provider.is_verified,
        "admin_tested_badge": provider.admin_tested_badge,
        "provider_is_verified": provider.is_verified,
        "provider_admin_tested_badge": provider.admin_tested_badge,
        "likes_count": service.likes_count,
        "is_own": is_own,
    }
