from django.db import models


class BotRegistrationSession(models.Model):
    class State(models.TextChoices):
        SELECT_ROLE = "select_role", "Select Role"
        PROVIDER_PHONE = "provider_phone", "Provider Phone"
        SECONDARY_PHONE = "secondary_phone", "Secondary Phone"
        CATEGORY = "category", "Category"
        TITLE = "title", "Title"
        DESCRIPTION = "description", "Description"
        LOCATION = "location", "Location"
        PRICES = "prices", "Prices"
        PHOTOS = "photos", "Photos"
        SUBMIT = "submit", "Submit"
        POLICY = "policy", "Policy"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    telegram_user_id = models.BigIntegerField(unique=True, db_index=True)
    chat_id = models.BigIntegerField(db_index=True)
    state = models.CharField(
        max_length=40,
        choices=State.choices,
        default=State.SELECT_ROLE,
        db_index=True,
    )
    city = models.CharField(
        max_length=150,
        blank=True,
        help_text="Temporary city field during registration.",
    )
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "bot_registration_sessions"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"RegistrationSession user={self.telegram_user_id} state={self.state}"
