from django.urls import path

from .views import miniapp_landing, miniapp_route_check

urlpatterns = [
    path("", miniapp_landing, name="miniapp-landing-api"),
    path("landing/", miniapp_landing, name="miniapp-landing-alt"),
    path("route-check/", miniapp_route_check, name="miniapp-route-check"),
]
