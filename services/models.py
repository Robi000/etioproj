from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import TelegramUser


class CityLocation(models.Model):
    """
    Stores city geographic boundaries using coordinates.
    """
    name = models.CharField(
        max_length=120,
        unique=True,
        db_index=True,
        help_text="Unique city name.",
    )
    top_left_x = models.DecimalField(max_digits=9, decimal_places=6)
    top_left_y = models.DecimalField(max_digits=9, decimal_places=6)
    top_right_x = models.DecimalField(max_digits=9, decimal_places=6)
    top_right_y = models.DecimalField(max_digits=9, decimal_places=6)
    bottom_right_x = models.DecimalField(max_digits=9, decimal_places=6)
    bottom_right_y = models.DecimalField(max_digits=9, decimal_places=6)
    bottom_left_x = models.DecimalField(max_digits=9, decimal_places=6)
    bottom_left_y = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        db_table = "city_locations"
        verbose_name = "City Location"
        verbose_name_plural = "City Locations"

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_city_for_coordinates(cls, x: Any, y: Any) -> str | None:
        if x is None or y is None:
            return None
        try:
            x_val = Decimal(str(x))
            y_val = Decimal(str(y))
        except (ValueError, TypeError, InvalidOperation):
            return None

        # Check bounds for each configured city
        for city in cls.objects.all():
            min_x = min(city.top_left_x, city.bottom_left_x, city.top_right_x, city.bottom_right_x)
            max_x = max(city.top_left_x, city.bottom_left_x, city.top_right_x, city.bottom_right_x)
            min_y = min(city.top_left_y, city.bottom_left_y, city.top_right_y, city.bottom_right_y)
            max_y = max(city.top_left_y, city.bottom_left_y, city.top_right_y, city.bottom_right_y)
            if min_x <= x_val <= max_x and min_y <= y_val <= max_y:
                return city.name
        return None


class ServiceCategory(models.Model):
    """
    Stores service categories used by provider service profiles.
    """

    name = models.CharField(
        max_length=120,
        unique=True,
        db_index=True,
        help_text="Unique service category name.",
    )
    active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Controls whether this category is available for marketplace use.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_categories"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="svc_category_name_idx"),
            models.Index(fields=["active"], name="svc_category_active_idx"),
        ]
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.name:
            self.name = " ".join(self.name.strip().split())
        if not self.name:
            raise ValidationError({"name": "Category name is required."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class ServiceProfile(models.Model):
    """
    Stores one marketplace service profile for one Telegram provider.
    """

    class LocationSource(models.TextChoices):
        GPS = "gps", "GPS"
        CITY_TEXT = "city_text", "City Text"
        BOTH = "both", "Both"

    class VisibilityStatus(models.TextChoices):
        ON = "on", "On"
        OFF = "off", "Off"

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    provider = models.OneToOneField(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="service_profile",
    )
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="service_profiles",
    )
    title = models.CharField(max_length=180)
    description = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    city_text = models.CharField(max_length=150, blank=True)
    location_source = models.CharField(
        max_length=20,
        choices=LocationSource.choices,
        default=LocationSource.CITY_TEXT,
        db_index=True,
    )
    visibility_status = models.CharField(
        max_length=10,
        choices=VisibilityStatus.choices,
        default=VisibilityStatus.ON,
        db_index=True,
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
    )
    approved_by = models.ForeignKey(
        TelegramUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_service_profiles",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Moderation & Performance fields
    admin_forced_hidden = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Admin-only: hide this provider from all discovery regardless of visibility status.",
    )
    denial_count = models.PositiveIntegerField(
        default=0,
        help_text="Total contact request denials (including timeouts) by this provider.",
    )
    acceptance_count = models.PositiveIntegerField(
        default=0,
        help_text="Total contact requests approved (admin or auto) for this provider.",
    )
    penalty_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Penalty expiry time. Provider is hidden from discovery until this time.",
    )
    penalty_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times a penalty has been applied to this service.",
    )
    prior_penalty_count = models.PositiveIntegerField(
        default=0,
        help_text="Tracks number of penalties applied (prior to latest).",
    )
    likes_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Total swipe-likes received on this service profile.",
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Admin-provided explanation when this service registration is rejected.",
    )
    location_update_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When admin last asked this provider to update their location.",
    )

    class Meta:
        db_table = "service_profiles"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["approval_status"], name="svc_profile_approval_idx"),
            models.Index(fields=["visibility_status"], name="svc_profile_visible_idx"),
            models.Index(fields=["location_source"], name="svc_profile_location_idx"),
            models.Index(fields=["city_text"], name="svc_profile_city_idx"),
            models.Index(fields=["created_at"], name="svc_profile_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["provider"],
                name="unique_service_profile_per_provider",
            )
        ]
        verbose_name = "Service Profile"
        verbose_name_plural = "Service Profiles"

    def __str__(self) -> str:
        return f"{self.title} - {self.provider.get_display_name()}"

    def clean(self) -> None:
        super().clean()

        if self.title:
            self.title = " ".join(self.title.strip().split())
        if self.description:
            self.description = self.description.strip()
        if self.city_text:
            self.city_text = " ".join(self.city_text.strip().split())

        if not self.title:
            raise ValidationError({"title": "Service title is required."})
        if not self.description:
            raise ValidationError({"description": "Service description is required."})

        self._validate_location()

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def _validate_location(self) -> None:
        has_gps = self.latitude is not None and self.longitude is not None
        has_city = bool(self.city_text)

        if self.location_source == self.LocationSource.GPS and not has_gps:
            raise ValidationError(
                {"location_source": "GPS location source requires latitude and longitude."}
            )

        if self.location_source == self.LocationSource.CITY_TEXT and not has_city:
            raise ValidationError(
                {"city_text": "City text is required when location source is city text."}
            )

        if self.location_source == self.LocationSource.BOTH and not (has_gps and has_city):
            raise ValidationError(
                {"location_source": "Both location source requires GPS coordinates and city text."}
            )

        if self.latitude is not None:
            latitude = Decimal(self.latitude)
            if latitude < Decimal("-90") or latitude > Decimal("90"):
                raise ValidationError({"latitude": "Latitude must be between -90 and 90."})

        if self.longitude is not None:
            longitude = Decimal(self.longitude)
            if longitude < Decimal("-180") or longitude > Decimal("180"):
                raise ValidationError({"longitude": "Longitude must be between -180 and 180."})

    @property
    def is_discoverable_candidate(self) -> bool:
        now = timezone.now()
        return (
            self.approval_status == self.ApprovalStatus.APPROVED
            and self.visibility_status == self.VisibilityStatus.ON
            and not self.provider.is_banned
            and not self.admin_forced_hidden
            and (self.penalty_until is None or self.penalty_until < now)
        )

    def has_at_least_one_price(self) -> bool:
        """
        Returns whether this service already has at least one valid price.

        This supports later service submission validation.
        """
        return self.prices.exists()

    def photo_count(self) -> int:
        return self.photos.count()


    def has_minimum_photos(self) -> bool:
        return self.photo_count() >= 1


    def can_add_photo(self) -> bool:
        return self.photo_count() < 3


class ServicePrice(models.Model):
    """
    Stores fixed time-based prices for a service profile.

    Allowed price types:
    - half_day
    - full_day
    - night
    """

    class PriceType(models.TextChoices):
        HALF_DAY = "half_day", "Half Day"
        FULL_DAY = "full_day", "Full Day"
        NIGHT = "night", "Night"

    service = models.ForeignKey(
        ServiceProfile,
        on_delete=models.CASCADE,
        related_name="prices",
        help_text="Service profile this price belongs to.",
    )
    price_type = models.CharField(
        max_length=20,
        choices=PriceType.choices,
        db_index=True,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price amount in ETB.",
    )

    class Meta:
        db_table = "service_prices"
        ordering = ["service", "price_type"]
        indexes = [
            models.Index(fields=["service"], name="svc_price_service_idx"),
            models.Index(fields=["price_type"], name="svc_price_type_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "price_type"],
                name="unique_price_type_per_service",
            ),
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="service_price_amount_positive",
            ),
        ]
        verbose_name = "Service Price"
        verbose_name_plural = "Service Prices"

    def __str__(self) -> str:
        return f"{self.service.title} - {self.get_price_type_display()}: {self.amount} ETB"

    def clean(self) -> None:
        super().clean()

        if self.amount is None:
            raise ValidationError({"amount": "Price amount is required."})

        if self.amount <= Decimal("0"):
            raise ValidationError({"amount": "Price amount must be greater than zero."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class ServicePhoto(models.Model):
    service = models.ForeignKey(
        ServiceProfile,
        on_delete=models.CASCADE,
        related_name="photos",
    )

    telegram_file_id = models.CharField(
        max_length=512,
    )

    image = models.ImageField(
        upload_to="service_photos/",
        blank=True,
        null=True,
    )

    order_index = models.PositiveSmallIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        db_table = "service_photos"

        ordering = [
            "order_index",
            "created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "service",
                    "order_index",
                ],
                name="unique_photo_order_per_service",
            )
        ]

    def clean(self):
        super().clean()

        if not self.telegram_file_id:
            raise ValidationError(
                {
                    "telegram_file_id": "Telegram file ID is required."
                }
            )

        photo_count = (
            ServicePhoto.objects
            .filter(service=self.service)
            .exclude(pk=self.pk)
            .count()
        )

        if photo_count >= 3:
            raise ValidationError(
                {
                    "service": "A service cannot have more than 3 photos."
                }
            )

    def delete(self, *args, **kwargs):
        if self.image:
            self.image.delete(save=False)
        super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PhotoChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    service = models.ForeignKey(
        ServiceProfile,
        on_delete=models.CASCADE,
        related_name="photo_change_requests",
    )
    new_file_id = models.CharField(max_length=512)
    order_index = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "photo_change_requests"
        ordering = ["-created_at"]

    @property
    def current_photo(self):
        return self.service.photos.filter(order_index=self.order_index).first()

    def __str__(self) -> str:
        return f"PhotoChange service={self.service_id} index={self.order_index} status={self.status}"


class ProviderDenialLog(models.Model):
    class DenialReason(models.TextChoices):
        MANUAL_REJECT = "manual_reject", "Manual Reject"
        TIMEOUT = "timeout", "Timeout (24h)"

    service = models.ForeignKey(
        ServiceProfile,
        on_delete=models.CASCADE,
        related_name="denial_logs",
    )
    reason = models.CharField(
        max_length=20,
        choices=DenialReason.choices,
    )
    contact_request = models.ForeignKey(
        "approvals.ContactRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "provider_denial_logs"
        indexes = [
            models.Index(fields=["service"], name="pdl_service_idx"),
            models.Index(fields=["created_at"], name="pdl_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Denial service={self.service_id} reason={self.reason}"