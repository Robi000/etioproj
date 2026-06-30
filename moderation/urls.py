from django.urls import path

from .views import moderation_route_check

urlpatterns = [
    path("", moderation_route_check, name="moderation-route-check"),
]