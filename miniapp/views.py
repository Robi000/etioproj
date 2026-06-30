import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger("marketplace")


def miniapp_landing(request: HttpRequest) -> HttpResponse:
    logger.info("Mini App landing page requested.")
    return render(request, "miniapp/app.html", {"bot_username": settings.TELEGRAM_BOT_USERNAME})


def favicon(request: HttpRequest) -> HttpResponse:
    return HttpResponse(status=204)


@api_view(["GET"])
@permission_classes([AllowAny])
def miniapp_route_check(request):
    logger.info("Miniapp API route check requested.")
    return Response(
        {
            "success": True,
            "app": "miniapp",
            "message": "Mini App API route is available.",
        }
    )
