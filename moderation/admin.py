from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "reporter",
        "reported_user",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "reporter__telegram_username",
        "reported_user__telegram_username",
        "reason",
    )

    autocomplete_fields = (
        "reporter",
        "reported_user",
    )

    ordering = (
        "-created_at",
    )