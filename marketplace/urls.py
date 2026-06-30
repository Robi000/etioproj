from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.views import (
    me,
    telegram_auth,
    update_customer_location,
    update_profile,
    update_profile_location,
    update_profile_visibility,
)
from adminpanel.views import (
    admin_dashboard,
    approve_contact,
    approve_photo_change,
    approve_service,
    dashboard_contact_action,
    dashboard_service_action,
    pending_contacts,
    pending_photo_changes,
    pending_services,
    process_timeouts,
    reject_contact,
    reject_photo_change,
    reject_service,
    request_location_updates,
    send_advertisement,
    send_mass_reminders,
    send_registration_reminder,
    send_surveys,
    toggle_provider_tested,
    toggle_provider_verified,
    toggle_service_admin_visibility,
    update_admin_settings,
)
from approvals.views import (
    contact_request_status,
    create_contact_request,
)
from matching.views import (
    discovery_grid,
    discovery_swipe,
)
from miniapp.views import favicon, miniapp_landing
from services.views import (
    create_my_service_photo,
    create_service,
    delete_my_service,
    delete_my_service_photo,
    get_my_service,
    service_photo_proxy,
    update_my_service,
    update_my_service_prices,
)
from swipes.views import (
    save_service,
    saved_services,
    swipe_dislike,
    swipe_like,
    unsave_service,
)

urlpatterns = [
    path("", miniapp_landing, name="miniapp-landing"),
    path("favicon.ico", favicon, name="favicon"),

    path("admin/", admin.site.urls),
    path("dashboard/admin/login/", auth_views.LoginView.as_view(template_name="adminpanel/login.html", next_page="adminpanel-dashboard"), name="adminpanel-login"),
    path("dashboard/admin/logout/", auth_views.LogoutView.as_view(next_page="adminpanel-login"), name="adminpanel-logout"),
    path("dashboard/admin/", admin_dashboard, name="adminpanel-dashboard"),
    path(
        "dashboard/admin/contact/<int:contact_request_id>/<str:action>/",
        dashboard_contact_action,
        name="adminpanel-dashboard-contact-action",
    ),
    path(
        "dashboard/admin/service/<int:service_id>/<str:action>/",
        dashboard_service_action,
        name="adminpanel-dashboard-service-action",
    ),

    path("api/health/", include("health.urls")),
    path("api/bot/", include("bot.urls")),

    path("api/auth/telegram/", telegram_auth, name="api-telegram-auth"),
    path("api/me/", me, name="api-me"),

    path("api/profile/", update_profile, name="api-profile"),
    path("api/profile/location/", update_profile_location, name="api-profile-location"),
    path("api/profile/customer-location/", update_customer_location, name="api-customer-location"),
    path("api/profile/visibility/", update_profile_visibility, name="api-profile-visibility"),

    path("api/service/", create_service, name="api-create-service"),
    path("api/service/me/", get_my_service, name="api-get-my-service"),
    path("api/service/me/update/", update_my_service, name="api-update-my-service"),
    path("api/service/me/delete/", delete_my_service, name="api-delete-my-service"),
    path("api/service/prices/", update_my_service_prices, name="api-update-my-service-prices"),
    path("api/service/photos/", create_my_service_photo, name="api-create-my-service-photo"),
    path("api/service/photos/<int:photo_id>/", delete_my_service_photo, name="api-delete-my-service-photo"),
    path("api/service/photo/<int:photo_id>/", service_photo_proxy, name="api-service-photo-proxy"),

    path("api/discovery/swipe/", discovery_swipe, name="api-discovery-swipe"),
    path("api/discovery/grid/", discovery_grid, name="api-discovery-grid"),

    path("api/swipe/like/", swipe_like, name="api-swipe-like"),
    path("api/swipe/dislike/", swipe_dislike, name="api-swipe-dislike"),
    path("api/swipe/save/", save_service, name="api-swipe-save"),
    path(
        "api/swipe/save/<int:service_id>/",
        unsave_service,
        name="api-swipe-unsave",
    ),
    path("api/swipe/saved/", saved_services, name="api-swipe-saved"),
    path("api/contact-request/", create_contact_request, name="api-contact-request"),
    path("api/contact-request/status/", contact_request_status, name="api-contact-request-status"),

    path("api/admin/services/pending/", pending_services, name="api-admin-services-pending"),
    path("api/admin/service/approve/", approve_service, name="api-admin-service-approve"),
    path("api/admin/service/reject/", reject_service, name="api-admin-service-reject"),
    path("api/admin/contacts/pending/", pending_contacts, name="api-admin-contacts-pending"),
    path("api/admin/contact/approve/", approve_contact, name="api-admin-contact-approve"),
    path("api/admin/contact/reject/", reject_contact, name="api-admin-contact-reject"),
    path("api/admin/settings/", update_admin_settings, name="api-admin-settings"),
    path(
        "api/admin/provider/<int:provider_id>/toggle-verified/",
        toggle_provider_verified,
        name="api-admin-toggle-verified",
    ),
    path(
        "api/admin/provider/<int:provider_id>/toggle-tested/",
        toggle_provider_tested,
        name="api-admin-toggle-tested",
    ),
    path(
        "api/admin/service/<int:service_id>/toggle-admin-visibility/",
        toggle_service_admin_visibility,
        name="api-admin-toggle-visibility",
    ),
    path(
        "api/admin/send-registration-reminder/",
        send_registration_reminder,
        name="api-admin-send-reminder",
    ),
    path(
        "api/admin/send-mass-reminders/",
        send_mass_reminders,
        name="api-admin-mass-reminders",
    ),
    path(
        "api/admin/process-timeouts/",
        process_timeouts,
        name="api-admin-process-timeouts",
    ),
    path(
        "api/admin/request-location-updates/",
        request_location_updates,
        name="api-admin-request-location-updates",
    ),
    path(
        "api/admin/photo-changes/pending/",
        pending_photo_changes,
        name="api-admin-photo-changes-pending",
    ),
    path(
        "api/admin/photo-change/<int:request_id>/approve/",
        approve_photo_change,
        name="api-admin-photo-change-approve",
    ),
    path(
        "api/admin/photo-change/<int:request_id>/reject/",
        reject_photo_change,
        name="api-admin-photo-change-reject",
    ),
    path(
        "api/admin/send-surveys/",
        send_surveys,
        name="api-admin-send-surveys",
    ),
    path(
        "api/admin/send-advertisement/",
        send_advertisement,
        name="api-admin-send-advertisement",
    ),

    path("api/accounts/", include("accounts.urls")),
    path("api/services/", include("services.urls")),
    path("api/swipes/", include("swipes.urls")),
    path("api/matching/", include("matching.urls")),
    path("api/approvals/", include("approvals.urls")),
    path("api/moderation/", include("moderation.urls")),
    path("api/verification/", include("verification.urls")),
    path("api/miniapp/", include("miniapp.urls")),
    path("api/adminpanel/", include("adminpanel.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
