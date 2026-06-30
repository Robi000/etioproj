from django.core.exceptions import ValidationError
from django.db import models

from services.models import ServiceProfile


class VerifiedBadge(models.Model):
    class BadgeType(models.TextChoices):
        MANUAL = "manual", "Manual"
        PAID = "paid", "Paid"

    service = models.OneToOneField(
        ServiceProfile,
        on_delete=models.CASCADE,
        related_name="verified_badge",
    )

    badge_type = models.CharField(
        max_length=20,
        choices=BadgeType.choices,
    )

    class Meta:
        db_table = "verified_badges"

    def clean(self):
        super().clean()

        if self.service.approval_status != (
            ServiceProfile.ApprovalStatus.APPROVED
        ):
            raise ValidationError(
                {
                    "service": (
                        "Only approved services "
                        "can receive verification."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.service.title} "
            f"({self.badge_type})"
        )