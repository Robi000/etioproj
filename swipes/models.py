from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import TelegramUser
from services.models import ServiceProfile


class SwipeHistory(models.Model):
    class SwipeStatus(models.TextChoices):
        LIKED = "liked", "Liked"
        DISLIKED = "disliked", "Disliked"
        SEEN = "seen", "Seen"

    customer = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="swipe_history",
    )

    service = models.ForeignKey(
        ServiceProfile,
        on_delete=models.CASCADE,
        related_name="swipe_history",
    )

    swipe_status = models.CharField(
        max_length=20,
        choices=SwipeStatus.choices,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    reset_at = models.DateTimeField(
        db_index=True,
        blank=True,
    )

    class Meta:
        db_table = "swipe_history"

        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=["customer"],
                name="swipe_customer_idx",
            ),
            models.Index(
                fields=["service"],
                name="swipe_service_idx",
            ),
            models.Index(
                fields=["reset_at"],
                name="swipe_reset_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.customer.is_banned:
            raise ValidationError(
                {
                    "customer": "Banned users cannot create swipe history."
                }
            )

    def save(self, *args, **kwargs):
        if not self.reset_at:
            if settings.DEBUG:
                self.reset_at = timezone.now()
            else:
                self.reset_at = timezone.now() + timedelta(days=1)

        self.full_clean()
        super().save(*args, **kwargs)


class SavedServiceRequest(models.Model):
    customer = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="saved_services",
    )
    service = models.ForeignKey(
        ServiceProfile,
        on_delete=models.CASCADE,
        related_name="saved_by",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        db_table = "saved_service_requests"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "service"],
                name="unique_saved_service_per_customer",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.customer} saved {self.service}"