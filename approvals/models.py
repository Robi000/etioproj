from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import TelegramUser
from services.models import ServiceProfile


class ContactRequest(models.Model):
    class Status(models.TextChoices):
        PROVIDER_PENDING = "provider_pending", "Provider Pending"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PROVIDER_REJECTED = "provider_rejected", "Provider Rejected"
        AUTO_APPROVED = "auto_approved", "Auto Approved"

    customer = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="contact_requests_sent",
    )

    provider = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="contact_requests_received",
    )

    service = models.ForeignKey(
        ServiceProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_requests",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    approved_by = models.ForeignKey(
        TelegramUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_contact_requests",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        db_table = "contact_requests"

        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=["customer"],
                name="contact_customer_idx",
            ),
            models.Index(
                fields=["provider"],
                name="contact_provider_idx",
            ),
            models.Index(
                fields=["service"],
                name="contact_service_idx",
            ),
            models.Index(
                fields=["status"],
                name="contact_status_idx",
            ),
            models.Index(
                fields=["provider", "status"],
                name="contact_provider_status_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.customer_id == self.provider_id:
            raise ValidationError(
                {
                    "provider": "Customer and provider cannot be the same user."
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.customer} -> "
            f"{self.provider} ({self.status})"
        )


class AdminSettings(models.Model):
    auto_approve_requests = models.BooleanField(
        default=False,
    )

    reset_days = models.PositiveIntegerField(
        default=6,
    )

    default_radius = models.PositiveIntegerField(
        default=30,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "admin_settings"

    def clean(self):
        super().clean()

        if self.reset_days < 1:
            raise ValidationError(
                {
                    "reset_days": "Reset days must be at least 1."
                }
            )

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        settings, _ = cls.objects.get_or_create(
            pk=1
        )
        return settings

    def __str__(self):
        return "System Settings"


NO_REASON_CHOICES = [
    ("price_change", "Change in price"),
    ("transport_cost", "Transport cost > 1000 ETB"),
    ("advance_too_high", "Advance payment > 30%"),
    ("provider_not_responding", "Provider not responding"),
    ("provider_no_show", "Provider didn't come after advance"),
    ("personal", "I don't like her"),
]


class CustomerSurvey(models.Model):
    contact_request = models.OneToOneField(
        ContactRequest,
        on_delete=models.CASCADE,
        related_name="survey",
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    response = models.CharField(
        max_length=10,
        choices=[("yes", "Yes"), ("no", "No")],
        blank=True,
    )
    responded_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    no_reason = models.CharField(
        max_length=50,
        choices=NO_REASON_CHOICES,
        blank=True,
    )

    class Meta:
        db_table = "customer_surveys"

    def __str__(self) -> str:
        return f"Survey for contact_request {self.contact_request_id}"
