from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import TelegramUser


class Report(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWED = "reviewed", "Reviewed"
        DISMISSED = "dismissed", "Dismissed"

    reporter = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="reports_submitted",
    )

    reported_user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="reports_received",
    )

    reason = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        db_table = "reports"

        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=["reporter"],
                name="report_reporter_idx",
            ),
            models.Index(
                fields=["reported_user"],
                name="report_target_idx",
            ),
            models.Index(
                fields=["status"],
                name="report_status_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.reporter_id == self.reported_user_id:
            raise ValidationError(
                {
                    "reported_user": "Users cannot report themselves."
                }
            )

        if not self.reason.strip():
            raise ValidationError(
                {
                    "reason": "Reason is required."
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.reporter} -> "
            f"{self.reported_user}"
        )