from __future__ import annotations

import mimetypes
import uuid
from typing import TYPE_CHECKING

import requests
from django.core.files.base import ContentFile

from bot.services import TelegramBotService, get_bot_api_session

if TYPE_CHECKING:
    from services.models import ServicePhoto


def store_photo_locally(photo: ServicePhoto) -> None:
    if not photo.telegram_file_id:
        return

    file_id = photo.telegram_file_id
    if file_id.startswith("http://") or file_id.startswith("https://"):
        file_url = file_id
    else:
        bot = TelegramBotService()
        file_url = bot.get_file_download_url(file_id)
        if not file_url:
            return

    try:
        session = requests.Session() if file_id.startswith("http") else get_bot_api_session()
        response = session.get(file_url, timeout=(4, 12))
    except Exception:
        return

    if not response.ok:
        return

    photo.image.delete(save=False)

    content_type = response.headers.get("Content-Type", "image/jpeg") or "image/jpeg"
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif"):
        ext = ".jpg"
    filename = f"photo_{photo.id}_{uuid.uuid4().hex[:8]}{ext}"
    photo.image.save(filename, ContentFile(response.content), save=True)
