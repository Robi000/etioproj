from django.contrib import admin

from .models import TelegramUser


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = (
        "telegram_id",
        "telegram_username",
        "first_name",
        "last_name",
        "phone_number",
        "role",
        "is_verified",
        "is_banned",
        "created_at",
    )
    list_filter = (
        "role",
        "is_verified",
        "is_banned",
        "created_at",
    )
    search_fields = (
        "telegram_id",
        "telegram_username",
        "first_name",
        "last_name",
        "phone_number",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
