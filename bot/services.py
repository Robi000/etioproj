import logging
from threading import local
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException, Timeout
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from urllib3.util.retry import Retry

from bot.networking import force_requests_ipv4, redact_telegram_token

logger = logging.getLogger("marketplace")

force_requests_ipv4()

MESSAGE_CONNECT_TIMEOUT = 4
MESSAGE_READ_TIMEOUT = 12
CALLBACK_CONNECT_TIMEOUT = 1
CALLBACK_READ_TIMEOUT = 2
BOT_API_MAX_ATTEMPTS = 2
CALLBACK_API_MAX_ATTEMPTS = 1
BOT_API_POOL_SIZE = 8
BOT_API_USER_AGENT = "telegram-marketplace-bot/1.0"

_thread_local = local()


class TelegramBotService:
    def __init__(self) -> None:
        if not settings.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env")

        self.token = settings.TELEGRAM_BOT_TOKEN
        self.api_base_url = settings.TELEGRAM_BOT_API_BASE_URL.rstrip("/")

    def send_start_menu(self, chat_id: int) -> bool:
        return self.send_text(
            chat_id=chat_id,
            text=(
                "✨ Welcome to the Telegram Service Marketplace አላችሁ ወይይ ?!\n\n"
                "Choose what you want to do next 👇"
            ),
            reply_markup=self.build_start_menu_keyboard(),
        )

    def build_start_menu_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [self.build_mini_app_button(text="🛒 Open Marketplace")],
                [
                    InlineKeyboardButton(
                        "🛠 Create Service",
                        callback_data="registration:create_service",
                    ),
                    InlineKeyboardButton(
                        "📋 My Service",
                        callback_data="registration:my_service",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔔 Notifications",
                        callback_data="notifications:open",
                    )
                ],
            ]
        )

    def build_reset_button(self) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            "🔄 Reset Registration",
            callback_data="registration:reset",
        )

    def build_role_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🛠 Provider",
                        callback_data="registration:role:provider",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🧭 Customer",
                        callback_data="registration:role:customer",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔁 Both",
                        callback_data="registration:role:both",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data="registration:cancel",
                    )
                ],
                [self.build_reset_button()],
            ]
        )

    def build_secondary_phone_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [["Skip Secondary Phone"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

    def build_category_keyboard(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "⚡ Electrician",
                        "callback_data": "registration:category:Electrician",
                    }
                ],
                [
                    {
                        "text": "🧽 Cleaner",
                        "callback_data": "registration:category:Cleaner",
                    }
                ],
                [
                    {
                        "text": "📚 Tutor",
                        "callback_data": "registration:category:Tutor",
                    }
                ],
                [
                    {
                        "text": "🔧 Mechanic",
                        "callback_data": "registration:category:Mechanic",
                    }
                ],
                [
                    {
                        "text": "🚰 Plumber",
                        "callback_data": "registration:category:Plumber",
                    }
                ],
                [
                    {
                        "text": "❌ Cancel",
                        "callback_data": "registration:cancel",
                    }
                ],
                [
                    {
                        "text": "🔄 Reset Registration",
                        "callback_data": "registration:reset",
                    }
                ],
            ]
        }

    def build_customer_category_keyboard(self) -> dict[str, Any]:
        from services.models import ServiceCategory

        emoji_by_name = {
            "Electrician": "⚡",
            "Cleaner": "🧽",
            "Tutor": "📚",
            "Mechanic": "🔧",
            "Plumber": "🚰",
        }
        categories = ServiceCategory.objects.filter(active=True).order_by("name")

        rows = []
        for category in categories:
            emoji = emoji_by_name.get(category.name, "🔎")
            rows.append(
                [
                    {
                        "text": f"{emoji} {category.name}",
                        "callback_data": f"customer:browse:category:{category.name}",
                    }
                ]
            )

        if not rows:
            rows.append(
                [
                    {
                        "text": "🔎 Browse all services",
                        "callback_data": "customer:browse:category:",
                    }
                ]
            )

        return {"inline_keyboard": rows}

    def build_price_keyboard(self, prices: dict | None = None) -> InlineKeyboardMarkup:
        prices = prices or {}

        def label(name: str, key: str) -> str:
            value = prices.get(key)
            if value:
                return f"✅ {name} — {value}"
            return f"➕ Set {name}"

        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        label("Half-Day Price", "half_day"),
                        callback_data="registration:price:half_day",
                    )
                ],
                [
                    InlineKeyboardButton(
                        label("Full-Day Price", "full_day"),
                        callback_data="registration:price:full_day",
                    )
                ],
                [
                    InlineKeyboardButton(
                        label("Night Price", "night"),
                        callback_data="registration:price:night",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✅ Done With Prices",
                        callback_data="registration:prices_done",
                    )
                ],
                [self.build_reset_button()],
                [
                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data="registration:cancel",
                    )
                ],
            ]
        )

    def build_photo_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Done With Photos",
                        callback_data="registration:photos_done",
                    )
                ],
                [self.build_reset_button()],
                [
                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data="registration:cancel",
                    )
                ],
            ]
        )

    def build_submit_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🚀 Submit Registration Draft",
                        callback_data="registration:submit",
                    )
                ],
                [self.build_reset_button()],
                [
                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data="registration:cancel",
                    )
                ],
            ]
        )

    def build_mini_app_keyboard(
        self,
        text: str,
        screen: str | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    self.build_mini_app_button(
                        text=text,
                        screen=screen,
                        query_params=query_params,
                    )
                ]
            ]
        )

    def build_my_service_status_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    self.build_mini_app_button(
                        text="📋 Open My Service",
                        screen="my-service",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔄 Refresh Status",
                        callback_data="registration:my_service",
                    )
                ],
            ]
        )

    def build_existing_registration_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📋 View My Profile",
                        callback_data="registration:my_service",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑 Delete Provider Profile",
                        callback_data="profile:delete_request",
                    )
                ],
            ]
        )

    def build_delete_profile_confirm_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Yes, delete this profile",
                        callback_data="profile:delete_confirm",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Keep my profile",
                        callback_data="profile:delete_cancel",
                    )
                ],
            ]
        )

    def build_provider_menu_keyboard(self, is_visible: bool = True) -> ReplyKeyboardMarkup:
        rows = [
            ["My Profile", "Edit Profile"],
            ["Go Offline" if is_visible else "Go Online"],
        ]
        return ReplyKeyboardMarkup(
            rows,
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True,
            input_field_placeholder="Manage your provider profile",
        )

    def build_offline_menu_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [["Go Online"]],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True,
            input_field_placeholder="Tap Go Online to become visible again",
        )

    def build_profile_edit_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Category", callback_data="profile:edit:category"),
                    InlineKeyboardButton("Age", callback_data="profile:edit:age"),
                ],
                [
                    InlineKeyboardButton("Description", callback_data="profile:edit:description"),
                ],
                [
                    InlineKeyboardButton("Primary Phone", callback_data="profile:edit:primary_phone"),
                    InlineKeyboardButton("Secondary Phone", callback_data="profile:edit:secondary_phone"),
                ],
                [
                    InlineKeyboardButton("GPS Location", callback_data="profile:edit:location"),
                ],
                [
                    InlineKeyboardButton("Prices", callback_data="profile:edit:prices"),
                    InlineKeyboardButton("Photos", callback_data="profile:edit:photos"),
                ],
                [
                    InlineKeyboardButton("Done", callback_data="registration:my_service"),
                ],
            ]
        )

    def build_profile_category_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Electrician", callback_data="profile:category:Electrician")],
                [InlineKeyboardButton("Cleaner", callback_data="profile:category:Cleaner")],
                [InlineKeyboardButton("Tutor", callback_data="profile:category:Tutor")],
                [InlineKeyboardButton("Mechanic", callback_data="profile:category:Mechanic")],
                [InlineKeyboardButton("Plumber", callback_data="profile:category:Plumber")],
                [InlineKeyboardButton("Cancel", callback_data="profile:edit")],
            ]
        )

    def build_profile_price_keyboard(self, prices: dict | None = None) -> InlineKeyboardMarkup:
        prices = prices or {}

        def label(name: str, key: str) -> str:
            value = prices.get(key)
            if value:
                return f"{name}: {value}"
            return f"Set {name}"

        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        label("Half-Day", "half_day"),
                        callback_data="profile:price:half_day",
                    )
                ],
                [
                    InlineKeyboardButton(
                        label("Full-Day", "full_day"),
                        callback_data="profile:price:full_day",
                    )
                ],
                [
                    InlineKeyboardButton(
                        label("Night", "night"),
                        callback_data="profile:price:night",
                    )
                ],
                [InlineKeyboardButton("Done", callback_data="profile:edit")],
            ]
        )

    def build_profile_photo_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Done With Photos", callback_data="profile:photos_done")],
                [InlineKeyboardButton("Back to Edit Menu", callback_data="profile:edit")],
            ]
        )

    def build_contact_request_decision_keyboard(
        self,
        contact_request_id: int,
    ) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Accept Service",
                        callback_data=f"contact:accept:{contact_request_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Reject Service",
                        callback_data=f"contact:reject:{contact_request_id}",
                    )
                ],
            ]
        )

    def build_policy_answer_keyboard(self, question_index: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Yes",
                        callback_data=f"policy:answer:{question_index}:yes",
                    ),
                    InlineKeyboardButton(
                        "No",
                        callback_data=f"policy:answer:{question_index}:no",
                    ),
                ]
            ]
        )

    def build_policy_retry_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Read Policy Again",
                        callback_data="policy:start",
                    )
                ]
            ]
        )

    def build_register_again_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📝 Register Again",
                        callback_data="registration:create_service",
                    )
                ]
            ]
        )

    def build_mini_app_button(
        self,
        text: str,
        screen: str | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> InlineKeyboardButton:
        mini_app_url = build_mini_app_url(
            screen=screen,
            query_params=query_params,
        )

        if mini_app_url.startswith("https://"):
            return InlineKeyboardButton(
                text,
                web_app=WebAppInfo(url=mini_app_url),
            )

        return InlineKeyboardButton(
            text,
            url=mini_app_url,
        )

    def remove_reply_keyboard(self) -> ReplyKeyboardRemove:
        return ReplyKeyboardRemove()

    def request_contact(self, chat_id: int) -> bool:
        keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📱 Share Primary Phone",
                        request_contact=True,
                    )
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        ok = self.send_text(
            chat_id=chat_id,
            text="📱 Step 2: tap the button below to share your primary phone number.",
            reply_markup=keyboard,
        )

        if ok:
            self.send_text(
                chat_id=chat_id,
                text="You can tap below to cancel and restart from the beginning.",
                reply_markup=InlineKeyboardMarkup([[self.build_reset_button()]]),
            )

        return ok

    def request_location(self, chat_id: int) -> bool:
        keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📍 Share GPS Location",
                        request_location=True,
                    )
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        return self.send_text(
            chat_id=chat_id,
            text="📍 Share your GPS location using the button below. Manual city text is disabled.",
            reply_markup=keyboard,
        )

    def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any | None = None,
    ) -> bool:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }

        serialized_reply_markup = serialize_reply_markup(reply_markup)

        if serialized_reply_markup is not None:
            payload["reply_markup"] = serialized_reply_markup

        ok = self.post_bot_api(
            method="sendMessage",
            payload=payload,
            timeout=(MESSAGE_CONNECT_TIMEOUT, MESSAGE_READ_TIMEOUT),
        )

        if ok:
            logger.info(
                "event=telegram_send_message_success chat_id=%s text_length=%s",
                chat_id,
                len(text),
            )

        return ok

    def send_photo(self, chat_id: int, photo_file_id: str, caption: str = "") -> bool:
        ok = self.post_bot_api(
            method="sendPhoto",
            payload={
                "chat_id": chat_id,
                "photo": photo_file_id,
                "caption": caption,
            },
            timeout=(MESSAGE_CONNECT_TIMEOUT, MESSAGE_READ_TIMEOUT),
        )

        if ok:
            logger.info(
                "event=telegram_send_photo_success chat_id=%s caption_length=%s",
                chat_id,
                len(caption),
            )
        return ok

    def get_file_download_url(self, file_id: str) -> str | None:
        try:
            response = get_bot_api_session().get(
                f"{self.api_base_url}/bot{self.token}/getFile",
                params={"file_id": file_id},
                timeout=(MESSAGE_CONNECT_TIMEOUT, MESSAGE_READ_TIMEOUT),
            )
        except RequestException as exc:
            safe_error = redact_telegram_token(exc, self.token)
            logger.warning(
                "event=telegram_get_file_failed error=%s",
                safe_error,
            )
            return None

        try:
            data = response.json()
        except ValueError:
            logger.warning(
                "event=telegram_get_file_invalid_json status_code=%s",
                response.status_code,
            )
            return None

        if not response.ok or not data.get("ok"):
            logger.warning(
                "event=telegram_get_file_error status_code=%s description=%s",
                response.status_code,
                data.get("description"),
            )
            return None

        file_path = data.get("result", {}).get("file_path")
        if not file_path:
            return None

        return f"{self.api_base_url}/file/bot{self.token}/{file_path}"

    def answer_callback(
        self,
        callback_query_id: str,
        text: str,
    ) -> bool:
        ok = self.post_bot_api(
            method="answerCallbackQuery",
            payload={
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": False,
            },
            timeout=(CALLBACK_CONNECT_TIMEOUT, CALLBACK_READ_TIMEOUT),
            max_attempts=CALLBACK_API_MAX_ATTEMPTS,
        )

        if ok:
            logger.info(
                "event=telegram_answer_callback_success callback_query_id=%s",
                callback_query_id,
            )
        return ok

    def post_bot_api(
        self,
        method: str,
        payload: dict[str, Any],
        timeout: tuple[int, int],
        max_attempts: int = BOT_API_MAX_ATTEMPTS,
    ) -> bool:
        for attempt in range(1, max_attempts + 1):
            try:
                response = get_bot_api_session().post(
                    f"{self.api_base_url}/bot{self.token}/{method}",
                    json=payload,
                    timeout=timeout,
                )
                break
            except Timeout as exc:
                safe_error = redact_telegram_token(exc, self.token)
                logger.warning(
                    "event=telegram_bot_api_timeout method=%s attempt=%s error=%s",
                    method,
                    attempt,
                    safe_error,
                )
                if attempt == max_attempts:
                    return False
            except RequestException as exc:
                safe_error = redact_telegram_token(exc, self.token)
                logger.warning(
                    "event=telegram_bot_api_request_failed method=%s attempt=%s error=%s",
                    method,
                    attempt,
                    safe_error,
                )
                if attempt == max_attempts:
                    return False
        else:
            return False

        try:
            data = response.json()
        except ValueError:
            logger.warning(
                "event=telegram_bot_api_invalid_json method=%s status_code=%s",
                method,
                response.status_code,
            )
            return False

        if not response.ok or not data.get("ok"):
            logger.warning(
                "event=telegram_bot_api_error method=%s status_code=%s description=%s",
                method,
                response.status_code,
                data.get("description"),
            )
            return False

        return True


def get_bot_api_session() -> requests.Session:
    session = getattr(_thread_local, "bot_api_session", None)
    if session is None:
        session = build_bot_api_session()
        _thread_local.bot_api_session = session

    return session


def build_bot_api_session() -> requests.Session:
    session = requests.Session()
    retry_policy = Retry(
        total=0,
        connect=0,
        read=0,
        redirect=0,
        status=0,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        pool_connections=BOT_API_POOL_SIZE,
        pool_maxsize=BOT_API_POOL_SIZE,
        max_retries=retry_policy,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "Connection": "keep-alive",
            "User-Agent": BOT_API_USER_AGENT,
        }
    )
    return session


def build_mini_app_url(
    screen: str | None = None,
    query_params: dict[str, Any] | None = None,
) -> str:
    base_url = settings.TELEGRAM_MINI_APP_URL or "http://localhost:3000"

    if not screen and not query_params:
        return base_url

    parts = urlsplit(base_url)
    query_items = dict(parse_qsl(parts.query, keep_blank_values=True))
    if screen:
        query_items["screen"] = screen
    if query_params:
        for key, value in query_params.items():
            if value is not None:
                query_items[key] = str(value)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query_items),
            parts.fragment,
        )
    )


def serialize_reply_markup(reply_markup: Any | None) -> dict[str, Any] | None:
    if reply_markup is None:
        return None

    if isinstance(reply_markup, dict):
        return reply_markup if reply_markup else None

    if hasattr(reply_markup, "to_dict"):
        serialized = reply_markup.to_dict()
        return serialized if serialized else None

    logger.warning(
        "event=telegram_invalid_reply_markup_type type=%s",
        type(reply_markup).__name__,
    )

    return None


def safe_get_chat_id(update_data: dict[str, Any]) -> int | None:
    message = update_data.get("message") or update_data.get("edited_message")
    callback_query = update_data.get("callback_query")

    if message:
        chat = message.get("chat", {})
        return chat.get("id")

    if callback_query:
        callback_message = callback_query.get("message", {})
        chat = callback_message.get("chat", {})
        return chat.get("id")

    return None
