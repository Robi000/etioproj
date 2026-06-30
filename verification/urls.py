from django.urls import path

from .views import verification_route_check

urlpatterns = [
    path("", verification_route_check, name="verification-route-check"),
]