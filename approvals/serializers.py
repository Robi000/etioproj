from rest_framework import serializers


class ContactRequestCreateSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(
        min_value=1,
    )


class ContactRequestStatusSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(
        min_value=1,
    )