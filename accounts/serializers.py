from decimal import Decimal
import re
from rest_framework import serializers

from .models import TelegramUser
from services.models import ServiceProfile


class TelegramAuthRequestSerializer(serializers.Serializer):
    init_data = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )


class TelegramUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    can_use_marketplace = serializers.SerializerMethodField()
    has_customer_location = serializers.SerializerMethodField()

    def get_has_customer_location(self, obj: TelegramUser) -> bool:
        return obj.has_customer_location

    class Meta:
        model = TelegramUser
        fields = (
            "id",
            "telegram_id",
            "telegram_username",
            "first_name",
            "last_name",
            "phone_number",
            "secondary_phone_number",
            "role",
            "is_verified",
            "is_banned",
            "display_name",
            "can_use_marketplace",
            "policy_accepted_at",
            "has_customer_location",
            "city",
            "likes_count",
            "admin_tested_badge",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_display_name(self, obj: TelegramUser) -> str:
        return obj.get_display_name()

    def get_can_use_marketplace(self, obj: TelegramUser) -> bool:
        return obj.can_use_marketplace


class TelegramAuthResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = TelegramUserSerializer()


class ProfileUpdateSerializer(serializers.Serializer):
    telegram_username = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        trim_whitespace=True,
    )
    first_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        trim_whitespace=True,
    )
    last_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        trim_whitespace=True,
    )
    phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=32,
        trim_whitespace=True,
    )
    secondary_phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=32,
        trim_whitespace=True,
    )
    role = serializers.ChoiceField(
        required=False,
        choices=TelegramUser.Role.choices,
    )

    
    def validate_secondary_phone_number(self, value):
        """Validate secondary phone number format if provided."""
        if value:
            # Remove whitespace
            cleaned = value.strip()
            
            # Check if it contains only valid characters (digits, +, -, spaces, parentheses)
            import re
            if not re.match(r'^[\d\s\+\-\(\)]{1,32}$', cleaned):
                raise serializers.ValidationError(
                    "Phone number contains invalid characters."
                )
            
            # Ensure minimum length
            digits_only = re.sub(r'[\s\+\-\(\)]', '', cleaned)
            if len(digits_only) < 7:
                raise serializers.ValidationError(
                    "Phone number must have at least 7 digits."
                )
            
            return cleaned
        return value


class ProfileLocationUpdateSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(
        required=False,
        allow_null=True,
        max_digits=9,
        decimal_places=6,
    )
    longitude = serializers.DecimalField(
        required=False,
        allow_null=True,
        max_digits=9,
        decimal_places=6,
    )
    city_text = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")
        city_text = attrs.get("city_text", "")

        has_latitude = latitude is not None
        has_longitude = longitude is not None
        has_city = bool(city_text.strip()) if isinstance(city_text, str) else False

        if has_latitude != has_longitude:
            raise serializers.ValidationError(
                "Latitude and longitude must be provided together."
            )

        if not has_city and not (has_latitude and has_longitude):
            raise serializers.ValidationError(
                "Provide either city_text or both latitude and longitude."
            )

        if latitude is not None:
            if latitude < Decimal("-90") or latitude > Decimal("90"):
                raise serializers.ValidationError(
                    {"latitude": "Latitude must be between -90 and 90."}
                )

        if longitude is not None:
            if longitude < Decimal("-180") or longitude > Decimal("180"):
                raise serializers.ValidationError(
                    {"longitude": "Longitude must be between -180 and 180."}
                )

        return attrs


class CustomerLocationSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
    )

    def validate(self, attrs):
        lat = attrs.get("latitude")
        lon = attrs.get("longitude")
        if lat is not None:
            if lat < Decimal("-90") or lat > Decimal("90"):
                raise serializers.ValidationError({"latitude": "Latitude must be between -90 and 90."})
        if lon is not None:
            if lon < Decimal("-180") or lon > Decimal("180"):
                raise serializers.ValidationError({"longitude": "Longitude must be between -180 and 180."})
        return attrs


class ProfileVisibilityUpdateSerializer(serializers.Serializer):
    visibility_status = serializers.ChoiceField(
        choices=ServiceProfile.VisibilityStatus.choices,
    )