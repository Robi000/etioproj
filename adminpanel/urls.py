from django.urls import path

from .views import (
    adminpanel_route_check,
    approve_contact,
    approve_service,
    pending_contacts,
    pending_services,
    reject_contact,
    reject_service,
    update_admin_settings,
)

urlpatterns = [
    path("", adminpanel_route_check, name="adminpanel-route-check"),
    path("admin/services/pending/", pending_services, name="adminpanel-services-pending"),
    path("admin/service/approve/", approve_service, name="adminpanel-service-approve"),
    path("admin/service/reject/", reject_service, name="adminpanel-service-reject"),
    path("admin/contacts/pending/", pending_contacts, name="adminpanel-contacts-pending"),
    path("admin/contact/approve/", approve_contact, name="adminpanel-contact-approve"),
    path("admin/contact/reject/", reject_contact, name="adminpanel-contact-reject"),
    path("admin/settings/", update_admin_settings, name="adminpanel-settings"),
]
