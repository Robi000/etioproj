from django.contrib import admin

from .models import (
    AdminSettings,
    ContactRequest,
)


@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "provider",
        "status",
        "approved_by",
        "approved_at",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "customer__telegram_username",
        "provider__telegram_username",
        "customer__telegram_id",
        "provider__telegram_id",
    )

    autocomplete_fields = (
        "customer",
        "provider",
        "approved_by",
    )

    ordering = (
        "-created_at",
    )


@admin.register(AdminSettings)
class AdminSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "auto_approve_requests",
        "reset_days",
        "default_radius",
        "updated_at",
    )

    def has_add_permission(self, request):
        return not AdminSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False