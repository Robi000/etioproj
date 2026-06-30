import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger("marketplace")


@api_view(["GET"])
@permission_classes([AllowAny])
def verification_route_check(request):
    logger.info("Verification API route check requested.")
    return Response(
        {
            "success": True,
            "app": "verification",
            "message": "Verification API route is available.",
        }
    )