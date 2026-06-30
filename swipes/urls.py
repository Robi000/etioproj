from django.urls import path

from .views import (
    save_service,
    saved_services,
    swipe_dislike,
    swipe_like,
    swipes_route_check,
    unsave_service,
)

urlpatterns = [
    path("", swipes_route_check, name="swipes-route-check"),
    path("swipe/like/", swipe_like, name="swipes-like"),
    path("swipe/dislike/", swipe_dislike, name="swipes-dislike"),
    path("swipe/save/", save_service, name="swipes-save"),
    path(
        "swipe/save/<int:service_id>/",
        unsave_service,
        name="swipes-unsave",
    ),
    path("swipe/saved/", saved_services, name="swipes-saved"),
]