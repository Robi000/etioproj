from django.contrib import admin

from .models import VerifiedBadge


@admin.register(VerifiedBadge)
class VerifiedBadgeAdmin(admin.ModelAdmin):
    list_display = (
        "service",
        "badge_type",
    )

    list_filter = (
        "badge_type",
    )

    search_fields = (
        "service__title",
    )

    autocomplete_fields = (
        "service",
    )