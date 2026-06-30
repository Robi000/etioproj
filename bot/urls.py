from django.urls import path

from .views import telegram_webhook

app_name = "bot"

urlpatterns = [
    path("webhook/", telegram_webhook, name="telegram-webhook"),
]
