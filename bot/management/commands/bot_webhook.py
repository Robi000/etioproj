import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from requests import Response
from requests.exceptions import RequestException

from bot.networking import force_requests_ipv4, redact_telegram_token
from bot.services import get_bot_api_session

logger = logging.getLogger("marketplace")

force_requests_ipv4()


class Command(BaseCommand):
    help = "Manage Telegram bot webhook: set, delete, or status."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "action",
            choices=["set", "delete", "status"],
            help="Webhook action to perform.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        action = options["action"]

        token = settings.TELEGRAM_BOT_TOKEN
        webhook_url = settings.TELEGRAM_WEBHOOK_URL
        secret = settings.BOT_WEBHOOK_SECRET

        logger.info("event=telegram_webhook_command action=%s", action)

        if not token:
            raise CommandError("TELEGRAM_BOT_TOKEN is missing in .env")

        if action == "set":
            if not webhook_url:
                raise CommandError("TELEGRAM_WEBHOOK_URL is missing in .env")
            if not secret:
                raise CommandError("BOT_WEBHOOK_SECRET is missing in .env")
            self.set_webhook(token, webhook_url, secret)
            return

        if action == "delete":
            self.delete_webhook(token)
            return

        if action == "status":
            self.webhook_status(token)
            return

    def telegram_api_url(self, token: str, method: str) -> str:
        return f"{settings.TELEGRAM_BOT_API_BASE_URL.rstrip('/')}/bot{token}/{method}"

    def set_webhook(self, token: str, webhook_url: str, secret: str) -> None:
        data = self.post_telegram_method(
            token=token,
            method="setWebhook",
            payload={
                "url": webhook_url,
                "secret_token": secret,
                "drop_pending_updates": True,
                "allowed_updates": [
                    "message",
                    "edited_message",
                    "callback_query",
                ],
            },
        )

        if not data.get("ok"):
            raise CommandError(f"Failed to set webhook: {data}")

        logger.info("event=telegram_webhook_set_success webhook_url=%s", webhook_url)
        self.stdout.write(self.style.SUCCESS("Telegram webhook set successfully."))
        self.stdout.write(f"Webhook URL: {webhook_url}")

    def delete_webhook(self, token: str) -> None:
        data = self.post_telegram_method(
            token=token,
            method="deleteWebhook",
            payload={"drop_pending_updates": True},
        )

        if not data.get("ok"):
            raise CommandError(f"Failed to delete webhook: {data}")

        logger.info("event=telegram_webhook_delete_success")
        self.stdout.write(self.style.SUCCESS("Telegram webhook deleted successfully."))

    def webhook_status(self, token: str) -> None:
        data = self.get_telegram_method(token=token, method="getWebhookInfo")

        if not data.get("ok"):
            raise CommandError(f"Failed to get webhook status: {data}")

        result = data.get("result", {})
        logger.info(
            "event=telegram_webhook_status_success webhook_url=%s pending_updates=%s",
            result.get("url"),
            result.get("pending_update_count"),
        )

        self.stdout.write(self.style.SUCCESS("Telegram webhook status:"))
        self.stdout.write(f"URL: {result.get('url')}")
        self.stdout.write(f"Pending updates: {result.get('pending_update_count')}")
        self.stdout.write(f"Last error date: {result.get('last_error_date')}")
        self.stdout.write(f"Last error message: {result.get('last_error_message')}")
        self.stdout.write(f"Allowed updates: {result.get('allowed_updates')}")

    def post_telegram_method(
        self,
        token: str,
        method: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = get_bot_api_session().post(
                self.telegram_api_url(token, method),
                json=payload,
                timeout=20,
            )
        except RequestException as exc:
            safe_error = redact_telegram_token(exc, token)
            logger.exception(
                "event=telegram_webhook_command_request_failed method=%s error=%s",
                method,
                safe_error,
            )
            raise CommandError(
                f"Telegram API request failed for {method}: {safe_error}"
            ) from exc

        return self.decode_telegram_response(response=response, method=method)

    def get_telegram_method(self, token: str, method: str) -> dict[str, Any]:
        try:
            response = get_bot_api_session().get(
                self.telegram_api_url(token, method),
                timeout=20,
            )
        except RequestException as exc:
            safe_error = redact_telegram_token(exc, token)
            logger.exception(
                "event=telegram_webhook_command_request_failed method=%s error=%s",
                method,
                safe_error,
            )
            raise CommandError(
                f"Telegram API request failed for {method}: {safe_error}"
            ) from exc

        return self.decode_telegram_response(response=response, method=method)

    def decode_telegram_response(
        self,
        response: Response,
        method: str,
    ) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            logger.exception(
                "event=telegram_webhook_command_bad_json method=%s status_code=%s",
                method,
                response.status_code,
            )
            raise CommandError(
                f"Telegram API returned invalid JSON for {method}."
            ) from exc

        if not response.ok:
            logger.warning(
                "event=telegram_webhook_command_http_error method=%s status_code=%s data=%s",
                method,
                response.status_code,
                data,
            )

        return data
