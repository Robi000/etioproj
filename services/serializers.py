from decimal import Decimal

from rest_framework import serializers

from .models import ServiceCategory, ServicePhoto, ServicePrice, ServiceProfile


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = (
            "id",
            "name",
            "active",
        )
        read_only_fields = fields


class ServicePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePrice
        fields = (
            "id",
            "price_type",
            "amount",
        )
        read_only_fields = (
            "id",
        )


class ServicePhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ServicePhoto
        fields = (
            "id",
            "telegram_file_id",
            "order_index",
            "created_at",
            "url",
        )
        read_only_fields = (
            "id",
            "created_at",
            "url",
        )

    def get_url(self, obj):
        return obj.image.url if obj.image else None


class ServicePhotoCreateSerializer(serializers.Serializer):
    telegram_file_id = serializers.CharField(
        max_length=512,
        allow_blank=False,
        trim_whitespace=True,
    )
    order_index = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=3,
    )


class ServiceProfileSerializer(serializers.ModelSerializer):
    category = ServiceCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=ServiceCategory.objects.filter(active=True),
        write_only=True,
    )
    prices = ServicePriceSerializer(
        many=True,
        read_only=True,
    )
    photos = ServicePhotoSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = ServiceProfile
        fields = (
            "id",
            "provider",
            "category",
            "category_id",
            "title",
            "description",
            "latitude",
            "longitude",
            "city_text",
            "location_source",
            "visibility_status",
            "approval_status",
            "rejection_reason",
            "approved_by",
            "approved_at",
            "prices",
            "photos",
            "denial_count",
            "acceptance_count",
            "penalty_count",
            "penalty_until",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "provider",
            "category",
            "approval_status",
            "rejection_reason",
            "approved_by",
            "approved_at",
            "prices",
            "photos",
            "denial_count",
            "acceptance_count",
            "penalty_count",
            "penalty_until",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        request = self.context.get("request") if self.context else None

        if request is not None:
            from accounts.views import get_telegram_user_from_auth_user

            telegram_user = get_telegram_user_from_auth_user(request.user)

            if telegram_user is not None:
                if not telegram_user.phone_number:
                    raise serializers.ValidationError(
                        "Primary phone number is required before creating or updating a provider service."
                    )

                if not telegram_user.telegram_username:
                    raise serializers.ValidationError(
                        "Telegram username is required before registering as a provider."
                    )
                
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        city_text = attrs.get("city_text", getattr(self.instance, "city_text", ""))

        has_latitude = latitude is not None
        has_longitude = longitude is not None
        has_city = bool(str(city_text).strip()) if city_text is not None else False

        if has_latitude != has_longitude:
            raise serializers.ValidationError(
                "Latitude and longitude must be provided together."
            )

        if not has_city and not (has_latitude and has_longitude):
            raise serializers.ValidationError(
                "Provide either city_text or both latitude and longitude."
            )

        if latitude is not None:
            latitude_decimal = Decimal(latitude)
            if latitude_decimal < Decimal("-90") or latitude_decimal > Decimal("90"):
                raise serializers.ValidationError(
                    {"latitude": "Latitude must be between -90 and 90."}
                )

        if longitude is not None:
            longitude_decimal = Decimal(longitude)
            if longitude_decimal < Decimal("-180") or longitude_decimal > Decimal("180"):
                raise serializers.ValidationError(
                    {"longitude": "Longitude must be between -180 and 180."}
                )

        return attrs

    def create(self, validated_data):
        self._set_location_source(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        merged_data = {
            "latitude": validated_data.get("latitude", instance.latitude),
            "longitude": validated_data.get("longitude", instance.longitude),
            "city_text": validated_data.get("city_text", instance.city_text),
        }

        self._set_location_source(merged_data)
        validated_data["location_source"] = merged_data["location_source"]

        return super().update(instance, validated_data)

    def _set_location_source(self, data):
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        city_text = data.get("city_text", "")

        has_gps = latitude is not None and longitude is not None
        has_city = bool(str(city_text).strip()) if city_text is not None else False

        if has_gps and has_city:
            data["location_source"] = ServiceProfile.LocationSource.BOTH
        elif has_gps:
            data["location_source"] = ServiceProfile.LocationSource.GPS
        else:
            data["location_source"] = ServiceProfile.LocationSource.CITY_TEXT


class ServicePriceInputSerializer(serializers.Serializer):
    price_type = serializers.ChoiceField(
        choices=ServicePrice.PriceType.choices,
    )
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


class ServicePricesUpdateSerializer(serializers.Serializer):
    prices = ServicePriceInputSerializer(
        many=True,
        allow_empty=False,
    )

    def validate_prices(self, prices):
        seen_price_types = set()

        for price in prices:
            price_type = price["price_type"]

            if price_type in seen_price_types:
                raise serializers.ValidationError(
                    f"Duplicate price type is not allowed: {price_type}"
                )

            seen_price_types.add(price_type)

        return prices
