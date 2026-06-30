from rest_framework import serializers

from services.models import ServiceProfile


class SwipeActionSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(
        min_value=1,
    )


class SaveServiceSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(min_value=1)

    def validate_service_id(self, value: int) -> int:
        if not ServiceProfile.objects.filter(
            id=value,
            approval_status=ServiceProfile.ApprovalStatus.APPROVED,
            visibility_status=ServiceProfile.VisibilityStatus.ON,
        ).exists():
            raise serializers.ValidationError(
                "Service is not available for saving."
            )
        return value