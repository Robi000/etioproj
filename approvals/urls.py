from django.urls import path

from .views import (
    approvals_route_check,
    contact_request_status,
    create_contact_request,
)

urlpatterns = [
    path("", approvals_route_check, name="approvals-route-check"),
    path("contact-request/", create_contact_request, name="approvals-contact-request"),
    path("contact-request/status/", contact_request_status, name="approvals-contact-request-status"),
]