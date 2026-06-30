from rest_framework import serializers

from approvals.models import AdminSettings, ContactRequest
from services.models import PhotoChangeRequest, ServicePhoto, ServicePrice, ServiceProfile


class AdminServiceActionSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(
        min_value=1,
    )
    rejection_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=1000,
    )


class AdminContactActionSerializer(serializers.Serializer):
    contact_request_id = serializers.IntegerField(
        min_value=1,
    )


class AdminSettingsUpdateSerializer(serializers.Serializer):
    auto_approve_requests = serializers.BooleanField(
        required=False,
    )
    reset_days = serializers.IntegerField(
        required=False,
        min_value=1,
    )
    default_radius = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "At least one setting field must be provided."
            )

        return attrs


class PhotoSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePhoto
        fields = ("order_index", "telegram_file_id")


class PriceSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePrice
        fields = ("price_type", "amount")


class AdminServiceSummarySerializer(serializers.ModelSerializer):
    provider_telegram_id = serializers.IntegerField(
        source="provider.telegram_id",
        read_only=True,
    )
    provider_username = serializers.CharField(
        source="provider.telegram_username",
        read_only=True,
    )
    provider_phone = serializers.CharField(
        source="provider.phone_number",
        read_only=True,
    )
    provider_secondary_phone = serializers.CharField(
        source="provider.secondary_phone_number",
        read_only=True,
    )
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    photos = PhotoSummarySerializer(many=True, read_only=True)
    prices = PriceSummarySerializer(many=True, read_only=True)

    class Meta:
        model = ServiceProfile
        fields = (
            "id",
            "provider_telegram_id",
            "provider_username",
            "provider_phone",
            "provider_secondary_phone",
            "category_name",
            "title",
            "description",
            "city_text",
            "location_source",
            "visibility_status",
            "approval_status",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
            "photos",
            "prices",
        )


class AdminContactRequestSummarySerializer(serializers.ModelSerializer):
    customer_telegram_id = serializers.IntegerField(
        source="customer.telegram_id",
        read_only=True,
    )
    provider_telegram_id = serializers.IntegerField(
        source="provider.telegram_id",
        read_only=True,
    )
    service_id = serializers.IntegerField(
        source="service.id",
        read_only=True,
    )
    service_title = serializers.CharField(
        source="service.title",
        read_only=True,
    )
    service_category = serializers.CharField(
        source="service.category.name",
        read_only=True,
    )

    class Meta:
        model = ContactRequest
        fields = (
            "id",
            "customer_telegram_id",
            "provider_telegram_id",
            "service_id",
            "service_title",
            "service_category",
            "status",
            "approved_by",
            "approved_at",
            "created_at",
        )


class AdminSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminSettings
        fields = (
            "auto_approve_requests",
            "reset_days",
            "default_radius",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "created_at",
            "updated_at",
        )


class PhotoChangeRequestSerializer(serializers.ModelSerializer):
    service_id = serializers.IntegerField(source="service.id", read_only=True)
    provider_telegram_id = serializers.IntegerField(
        source="service.provider.telegram_id", read_only=True
    )
    provider_username = serializers.CharField(
        source="service.provider.telegram_username", read_only=True
    )
    service_title = serializers.CharField(source="service.title", read_only=True)
    category_name = serializers.CharField(
        source="service.category.name", read_only=True
    )

    class Meta:
        model = PhotoChangeRequest
        fields = (
            "id",
            "service_id",
            "provider_telegram_id",
            "provider_username",
            "service_title",
            "category_name",
            "new_file_id",
            "order_index",
            "status",
            "created_at",
            "approved_at",
        )
