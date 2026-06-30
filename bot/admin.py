from django.contrib import admin

from .models import BotRegistrationSession


@admin.register(BotRegistrationSession)
class BotRegistrationSessionAdmin(admin.ModelAdmin):
    list_display = (
        "telegram_user_id",
        "chat_id",
        "state",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "state",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "telegram_user_id",
        "chat_id",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = (
        "-updated_at",
    )