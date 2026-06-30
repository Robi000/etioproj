from django.contrib import admin

from .models import (
    ServiceCategory,
    ServiceProfile,
    ServicePrice,
    ServicePhoto,
)


class ServicePriceInline(admin.TabularInline):
    model = ServicePrice
    extra = 0
    fields = (
        "price_type",
        "amount",
    )


class ServicePhotoInline(admin.TabularInline):
    model = ServicePhoto

    extra = 0

    fields = (
        "order_index",
        "telegram_file_id",
        "created_at",
    )

    readonly_fields = (
        "created_at",
    )

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "active",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "active",
        "created_at",
    )
    search_fields = (
        "name",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = ("name",)


@admin.register(ServiceProfile)
class ServiceProfileAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "provider",
        "category",
        "city_text",
        "location_source",
        "visibility_status",
        "approval_status",
        "approved_by",
        "approved_at",
        "created_at",
    )
    list_filter = (
        "category",
        "location_source",
        "visibility_status",
        "approval_status",
        "created_at",
    )
    search_fields = (
        "title",
        "description",
        "city_text",
        "provider__telegram_id",
        "provider__telegram_username",
        "provider__first_name",
        "provider__last_name",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    autocomplete_fields = (
        "provider",
        "category",
        "approved_by",
    )
    inlines = [
    ServicePriceInline,
    ServicePhotoInline,
]
    ordering = ("-created_at",)


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = (
        "service",
        "price_type",
        "amount",
    )
    list_filter = (
        "price_type",
    )
    search_fields = (
        "service__title",
        "service__provider__telegram_id",
        "service__provider__telegram_username",
    )
    autocomplete_fields = (
        "service",
    )
    ordering = (
        "service",
        "price_type",
    )
