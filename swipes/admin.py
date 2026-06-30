from django.contrib import admin

from .models import SwipeHistory


@admin.register(SwipeHistory)
class SwipeHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "service",
        "swipe_status",
        "created_at",
        "reset_at",
    )

    list_filter = (
        "swipe_status",
        "created_at",
    )

    search_fields = (
        "customer__telegram_id",
        "customer__telegram_username",
        "service__title",
    )

    autocomplete_fields = (
        "customer",
        "service",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "created_at",
    )