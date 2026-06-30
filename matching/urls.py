from django.urls import path

from .views import (
    discovery_grid,
    discovery_swipe,
    matching_route_check,
)

urlpatterns = [
    path("", matching_route_check, name="matching-route-check"),
    path("discovery/swipe/", discovery_swipe, name="matching-discovery-swipe"),
    path("discovery/grid/", discovery_grid, name="matching-discovery-grid"),
]