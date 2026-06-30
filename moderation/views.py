import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger("marketplace")


@api_view(["GET"])
@permission_classes([AllowAny])
def moderation_route_check(request):
    logger.info("Moderation API route check requested.")
    return Response(
        {
            "success": True,
            "app": "moderation",
            "message": "Moderation API route is available.",
        }
    )