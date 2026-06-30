from django.urls import path

from .views import (
    accounts_route_check,
    me,
    telegram_auth,
    update_profile,
    update_profile_location,
    update_profile_visibility,
)

urlpatterns = [
    path("", accounts_route_check, name="accounts-route-check"),
    path("auth/telegram/", telegram_auth, name="accounts-telegram-auth"),
    path("me/", me, name="accounts-me"),
    path("profile/", update_profile, name="accounts-profile"),
    path("profile/location/", update_profile_location, name="accounts-profile-location"),
    path("profile/visibility/", update_profile_visibility, name="accounts-profile-visibility"),
]