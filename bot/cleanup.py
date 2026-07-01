from __future__ import annotations

import logging
from collections.abc import Iterator

from django.apps import apps
from django.db import connection
from django.db.models import Model

logger = logging.getLogger("marketplace")

MODEL_DELETE_ORDER = [
    "swipes.SwipeHistory",
    "swipes.SavedServiceRequest",
    "approvals.CustomerSurvey",
    "approvals.ContactRequest",
    "services.ProviderDenialLog",
    "services.PhotoChangeRequest",
    "services.ServicePhoto",
    "services.ServicePrice",
    "services.ServiceProfile",
    "services.CityLocation",
    "services.ServiceCategory",
    "verification.VerifiedBadge",
    "moderation.Report",
    "bot.BotRegistrationSession",
    "approvals.AdminSettings",
    "accounts.TelegramUser",
    "authtoken.Token",
    "sessions.Session",
    "admin.LogEntry",
    "auth.User",
    "auth.Group",
    "auth.Permission",
    "contenttypes.ContentType",
]


def _iter_models() -> Iterator[type[Model]]:
    for path in MODEL_DELETE_ORDER:
        app_label, model_name = path.split(".")
        model = apps.get_model(app_label, model_name)
        if model is not None:
            yield model


class DataCleanupManager:
    def delete_all(self) -> dict[str, int]:
        results: dict[str, int] = {}

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF;")

        for model in _iter_models():
            label = f"{model._meta.app_label}.{model._meta.model_name}"
            try:
                count = model.objects.count()
                if count == 0:
                    results[label] = 0
                    continue
                model.objects.all().delete()
                results[label] = count
            except Exception as exc:
                logger.warning("Failed to delete %s: %s", label, exc)
                results[label] = -1

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("DELETE FROM sqlite_sequence;")

        return results
