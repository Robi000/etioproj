from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class TelegramUser(models.Model):
    """
    Stores Telegram identity and marketplace-specific user state.

    This model intentionally does not replace Django's built-in auth user.
    Django's built-in User remains available for admin login and internal staff.
    TelegramUser is used for marketplace users coming from Telegram Bot or Mini App.
    """

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        PROVIDER = "provider", "Provider"
        ADMIN = "admin", "Admin"
        BOTH = "both", "Both"

    telegram_id = models.BigIntegerField(
        unique=True,
        db_index=True,
        help_text="Unique Telegram user ID.",
    )
    telegram_username = models.CharField(
        max_length=150,
        blank=True,
        help_text="Telegram username without @ when available.",
    )
    first_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Telegram first name when available.",
    )
    last_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Telegram last name when available.",
    )
    phone_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="Phone number shared through Telegram contact flow when available.",
    )
    secondary_phone_number = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Optional secondary phone number for contact sharing.",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        db_index=True,
    )
    is_verified = models.BooleanField(
        default=False,
        db_index=True,
    )
    is_banned = models.BooleanField(
        default=False,
        db_index=True,
    )
    policy_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the user passed the Telegram policy verification test.",
    )
    policy_version = models.CharField(
        max_length=20,
        blank=True,
        help_text="Policy version accepted by the Telegram user.",
    )
    policy_failed_attempts = models.PositiveIntegerField(
        default=0,
        help_text="Number of failed policy verification attempts.",
    )
    policy_blocked_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Temporary block window after a failed policy verification.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # Added fields for Phase 1
    city = models.CharField(
        max_length=150,
        blank=True,
        help_text="City matched from GPS location coordinates.",
    )
    customer_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Customer GPS latitude for proximity matching.",
    )
    customer_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Customer GPS longitude for proximity matching.",
    )
    customer_location_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When customer last submitted their GPS location.",
    )
    last_interaction_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Timestamp of user's last interaction with the bot or mini app.",
    )
    likes_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Total number of swipe-likes received by this provider.",
    )
    admin_tested_badge = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Admin has personally tested and verified this provider.",
    )

    class Meta:
        db_table = "telegram_users"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["telegram_id"], name="tg_user_telegram_id_idx"),
            models.Index(fields=["role"], name="tg_user_role_idx"),
            models.Index(fields=["is_banned"], name="tg_user_banned_idx"),
            models.Index(fields=["is_verified"], name="tg_user_verified_idx"),
            models.Index(fields=["policy_accepted_at"], name="tg_user_policy_idx"),
            models.Index(fields=["customer_latitude", "customer_longitude"], name="tg_user_cust_loc_idx"),
            models.Index(fields=["last_interaction_at"], name="tg_user_last_interact_idx"),
        ]
        verbose_name = "Telegram User"
        verbose_name_plural = "Telegram Users"

    def __str__(self) -> str:
        display_name = self.get_display_name()
        return f"{display_name} ({self.telegram_id})"

    def clean(self) -> None:
        super().clean()

        if self.telegram_id <= 0:
            raise ValidationError({"telegram_id": "Telegram ID must be a positive integer."})

        if self.telegram_username:
            cleaned_username = self.telegram_username.strip().lstrip("@")
            if " " in cleaned_username:
                raise ValidationError(
                    {"telegram_username": "Telegram username must not contain spaces."}
                )
            self.telegram_username = cleaned_username

        if self.phone_number:
            self.phone_number = self.phone_number.strip()

        if self.secondary_phone_number:
            self.secondary_phone_number = self.secondary_phone_number.strip()

        # GPS validation
        if (self.customer_latitude is not None) != (self.customer_longitude is not None):
            raise ValidationError("Both customer latitude and longitude must be provided together.")

        if self.customer_latitude is not None and self.customer_longitude is not None:
            if self.customer_latitude < -90 or self.customer_latitude > 90:
                raise ValidationError({"customer_latitude": "Latitude must be between -90 and 90."})
            if self.customer_longitude < -180 or self.customer_longitude > 180:
                raise ValidationError({"customer_longitude": "Longitude must be between -180 and 180."})

            # Check if within Ethiopia bounding box
            if not (3.4 <= float(self.customer_latitude) <= 15.0 and 33.0 <= float(self.customer_longitude) <= 48.0):
                import logging
                logger = logging.getLogger("marketplace")
                logger.warning(
                    "Customer GPS location is outside Ethiopia's bounding box: lat=%s, lon=%s",
                    self.customer_latitude,
                    self.customer_longitude,
                )

            # Auto-assign city based on coordinates (longitude is X, latitude is Y)
            from services.models import CityLocation
            city_name = CityLocation.get_city_for_coordinates(self.customer_longitude, self.customer_latitude)
            if city_name:
                self.city = city_name

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def get_display_name(self) -> str:
        full_name = f"{self.first_name} {self.last_name}".strip()

        if full_name:
            return full_name

        if self.telegram_username:
            return f"@{self.telegram_username}"

        return "Telegram User"

    @property
    def can_use_marketplace(self) -> bool:
        return not self.is_banned

    def has_accepted_policy(self, version: str) -> bool:
        return bool(
            self.policy_accepted_at
            and self.policy_version == version
        )

    @property
    def has_customer_location(self) -> bool:
        return self.customer_latitude is not None and self.customer_longitude is not None

    def update_last_interaction(self, save: bool = True) -> None:
        self.last_interaction_at = timezone.now()
        if save:
            type(self).objects.filter(pk=self.pk).update(last_interaction_at=self.last_interaction_at)
