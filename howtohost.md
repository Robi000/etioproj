# How To Host Your Django Telegram Bot on cPanel Shared Hosting

This guide is specific to the project in `C:\Users\rabeb\OneDrive\Desktop\personalV1`.
It was written after scanning the project tree, reading the Django settings, URL maps,
models, views, Telegram bot modules, environment files, custom commands, static/media
directories, scripts, and deployment checks.

Use these placeholders consistently:

- `<CPANEL_USER>`: your cPanel username.
- `<YOUR_DOMAIN>`: your real domain, for example `example.com`.
- `<APP_ROOT>`: `/home/<CPANEL_USER>/repositories/personalV1`.
- `<PUBLIC_HTML>`: `/home/<CPANEL_USER>/public_html`.
- `<VENV_PYTHON>`: the Python path shown by cPanel Setup Python App, usually `/home/<CPANEL_USER>/virtualenv/repositories/personalV1/3.12/bin/python`.
- `<BOT_TOKEN>`: your Telegram bot token.
- `<BOT_SECRET>`: a long random webhook secret.
- `<ADMIN_TOKEN>`: a DRF token for a Django staff/superuser or linked Telegram admin account.

## PROJECT ANALYSIS SUMMARY

### Basic Information

- Project name: `marketplace`.
- Project type: Django + Django REST Framework backend, Telegram Bot webhook, Telegram Mini App, admin dashboard.
- Local path analyzed: `C:\Users\rabeb\OneDrive\Desktop\personalV1`.
- Django version: `4.2.11`.
- Local Python version: `3.12.7`.
- cPanel Python target: prefer Python `3.12` if available; Python `3.11` is acceptable for Django 4.2.11 if cPanel does not offer 3.12.
- Number of project apps: 11 custom apps.
- Custom apps:
  - `accounts`: Telegram user profiles, Mini App auth token creation, provider/customer profile APIs.
  - `services`: service categories, provider profiles, prices, Telegram photo references, photo proxy, average price endpoint.
  - `swipes`: like/dislike history and saved service requests.
  - `matching`: swipe/grid discovery and ranking logic.
  - `approvals`: contact request workflow, usage limits, admin settings, surveys.
  - `bot`: Telegram webhook dispatcher, registration state machine, bot keyboards, notifications, management commands.
  - `miniapp`: Mini App landing page at `/`.
  - `adminpanel`: Django admin-style marketplace dashboard and admin APIs.
  - `moderation`: user reports.
  - `verification`: service verification badge model.
  - `health`: `/api/health/`.

### Directory Inventory And Purposes

- `.git/`: Git metadata.
- `.pytest_cache/`: local pytest cache; do not upload.
- `accounts/`: Telegram user model, auth/profile views, serializers, tests, migrations.
- `adminpanel/`: admin dashboard views, serializers, tests, admin APIs, batch endpoints.
- `approvals/`: contact request models, workflow helpers, usage limits, serializers, tests.
- `bot/`: Telegram bot webhook, dispatcher, handlers, keyboards, registration state, notification helpers, management commands.
- `health/`: health endpoint.
- `kml datas/`: KML city/location source files; not required at runtime unless you use them for future imports.
- `logs/`: local `django.log` and `error.log`; do not upload old logs.
- `marketplace/`: Django project package with settings, URL routing, WSGI/ASGI, API exception handler.
- `matching/`: discovery API and discovery card serializer.
- `media/`: local media directory; currently empty.
- `miniapp/`: Mini App Django view and auth tests.
- `moderation/`: report model/API placeholder.
- `services/`: service/category/photo/price models and APIs.
- `static/`: local static source directory; currently empty.
- `swipes/`: swipe and saved service APIs/models.
- `templates/`: inline Mini App HTML/CSS/JS and admin dashboard templates.
- `tests/`: integration and routing tests.
- `venv/`: local virtualenv; do not upload.
- `verification/`: verified badge model/API placeholder.

Top-level files:

- `.env`: local environment file; values are set but redacted in this guide.
- `.env.example`: development defaults.
- `.gitignore`: excludes `venv/`, `.env`, `db.sqlite3`, pyc/cache/build artifacts.
- `db.sqlite3`: local SQLite database; do not use as the production database.
- `manage.py`: standard Django CLI entrypoint.
- `pytest.ini`, `conftest.py`: pytest configuration.
- `README.md`, `COMMANDS.md`, `SYSTEM_STATE.md`, `1.md` to `5.md`, `task.md`: project notes/requirements.
- `a.sh`: local Cloudflare Tunnel helper.
- `b.sh`: local webhook helper.
- `c.sh`: local runserver helper.
- `start.sh`: stale local runserver helper pointing to `personal proj`, not this folder.

### Database

- Current backend: SQLite.
- Current `DATABASES` in `marketplace/settings.py`:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

- `.env.example` contains `DATABASE_URL=sqlite:///db.sqlite3`, but `settings.py` does not read `DATABASE_URL`.
- Production recommendation: convert to MySQL/MariaDB on cPanel.
- Reason: this project uses Telegram webhooks, token auth, admin batch endpoints, contact requests, and in-process background threads. Local logs already show historical SQLite lock errors, which are expected under concurrent webhook traffic.
- If SQLite is kept temporarily, it must be outside `public_html`, writable by Passenger, and backed up often. This is not recommended.

### Static & Media Files

- Current `STATIC_URL`: `static/`.
- Current `STATIC_ROOT`: `BASE_DIR / "staticfiles"`.
- Current `STATICFILES_DIRS`: not set.
- Current `MEDIA_URL`: `media/`.
- Current `MEDIA_ROOT`: `BASE_DIR / "media"`.
- Local `static/`: exists, 0 files.
- Local `media/`: exists, 0 files.
- Local `staticfiles/`: does not exist yet.
- Local templates size: about 0.187 MB.
- Local non-venv/non-git project size: about 4.95 MB.
- `collectstatic --dry-run --noinput` found 160 static files, all from Django admin and DRF packages.
- Does project use Whitenoise? No.
- File uploads: no `FileField` or `ImageField` are used. Provider photos are stored as Telegram file IDs in `ServicePhoto.telegram_file_id` and proxied through `/api/service/photo/<photo_id>/`.
- Static/media URL pattern issue: `marketplace/urls.py` only adds `static(settings.MEDIA_URL, ...)` when `DEBUG=True`. With `DEBUG=False`, Django will not serve `/media/`. For this project that is mostly okay because service photos are proxied from Telegram, but any future local media files need Apache/cPanel serving.

### Environment Variables Required

From `marketplace/settings.py` and `.env.example`:

- `SECRET_KEY`: Django secret key. Default in code is unsafe: `django-insecure-dev-key`.
- `DEBUG`: currently defaults to `True`. Must be `False` in production.
- `ALLOWED_HOSTS`: comma-separated hosts. Default: `localhost,127.0.0.1`.
- `CORS_ALLOWED_ORIGINS`: comma-separated origins. Default: `http://localhost:3000,http://localhost:8000`.
- `TELEGRAM_BOT_TOKEN`: required for bot sends, Mini App auth validation, Telegram file proxy.
- `TELEGRAM_BOT_USERNAME`: used in Mini App meta tag and deep links.
- `TELEGRAM_MINI_APP_URL`: used by bot Mini App buttons. Default in `build_mini_app_url()` fallback is `http://localhost:3000`.
- `TELEGRAM_WEBHOOK_URL`: used by `python manage.py bot_webhook set`.
- `TELEGRAM_BOT_API_BASE_URL`: default `https://api.telegram.org`.
- `BOT_WEBHOOK_SECRET`: required by `/api/bot/webhook/`.
- `BOT_WEBHOOK_ASYNC`: default `True`; controls in-process background dispatch.
- `LOG_LEVEL`: default `DEBUG`.

Recommended production variables to add:

- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` for cPanel MySQL.
- `CSRF_TRUSTED_ORIGINS`, for example `https://<YOUR_DOMAIN>,https://www.<YOUR_DOMAIN>`.
- `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `STATIC_ROOT`, `MEDIA_ROOT` if you adopt the production settings snippets below.

### Telegram Bot Configuration

- Library used: `python-telegram-bot==21.0` for keyboard/markup objects.
- HTTP used for Telegram API calls: `requests==2.31.0` with a pooled session.
- Webhook URL path inside Django: `/api/bot/webhook/`.
- Full production webhook URL: `https://<YOUR_DOMAIN>/api/bot/webhook/`.
- Webhook security: `bot/views.py` requires header `X-Telegram-Bot-Api-Secret-Token` to equal `BOT_WEBHOOK_SECRET`.
- Polling or webhook: webhook.
- Webhook management command: `python manage.py bot_webhook set|delete|status`.
- Webhook allowed updates: `message`, `edited_message`, `callback_query`.
- Mini App URL: generated by `bot.services.build_mini_app_url()` using `TELEGRAM_MINI_APP_URL`; screen query param is added when needed.
- Important: direct browser access to `/` loads the Mini App shell, but API auth requires valid Telegram `initData`. For real use, open the Mini App from Telegram.
- Scheduler: no Celery, no django-apscheduler. The project has authenticated admin HTTP endpoints intended for cron:
  - `POST /api/admin/process-timeouts/`
  - `POST /api/admin/request-location-updates/`
  - `POST /api/admin/send-surveys/`
  - `POST /api/admin/send-advertisement/`
  - `POST /api/admin/send-mass-reminders/`

### Dependencies With System Requirements

There is no `requirements.txt`, `pyproject.toml`, `Pipfile`, or `poetry.lock` in the repo. The active virtualenv contains:

- `Django==4.2.11`
- `djangorestframework==3.14.0`
- `django-cors-headers==4.3.1`
- `python-decouple==3.8`
- `python-telegram-bot==21.0`
- `requests==2.31.0`
- `Pillow==10.1.0`
- `httpx==0.28.1`, `httpcore==1.0.9`, `h11==0.16.0`, `anyio==4.14.0`
- `certifi==2026.6.17`, `charset-normalizer==3.4.7`, `idna==3.18`, `urllib3==2.7.0`
- `asgiref==3.11.1`, `sqlparse==0.5.5`, `pytz==2026.2`, `tzdata==2026.2`
- test/dev packages: `pytest`, `pytest-django`, `pytest-cov`, `coverage`, `pluggy`, `iniconfig`, `packaging`, `colorama`

Production system-level notes:

- `Pillow==10.1.0`: may require JPEG/zlib libraries. The current models do not use `ImageField`, so Pillow may be removable if you confirm no runtime import uses it.
- MySQL support is not installed. Add either:
  - `mysqlclient==2.2.4` or newer: preferred if cPanel can compile/install it; requires MySQL/MariaDB client development libraries.
  - `PyMySQL==1.1.1`: pure Python fallback when `mysqlclient` cannot be installed.
- No PostgreSQL dependency is present.
- No `lxml` dependency is present.
- No `whitenoise` dependency is present.

### Settings.py Full Analysis

Current `marketplace/settings.py` summary:

- Imports: `Path`, `decouple.config`, `decouple.Csv`, `os`.
- `BASE_DIR`: project root.
- `LOG_DIR`: `BASE_DIR / "logs"` and `LOG_DIR.mkdir(exist_ok=True)` runs at import time.
- `SECRET_KEY`: `config("SECRET_KEY", default="django-insecure-dev-key")`.
- `DEBUG`: `config("DEBUG", default=True, cast=bool)`.
- `ENV_ALLOWED_HOSTS`: `config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())`.
- `ALLOWED_HOSTS`: `["*"] if DEBUG else ENV_ALLOWED_HOSTS`.
- `INSTALLED_APPS`:
  - Django: `admin`, `auth`, `contenttypes`, `sessions`, `messages`, `staticfiles`
  - Third-party: `rest_framework`, `rest_framework.authtoken`, `corsheaders`
  - Project: `accounts`, `services`, `swipes`, `matching`, `approvals`, `bot`, `miniapp`, `moderation`, `adminpanel`, `verification`, `health`
- `MIDDLEWARE`:
  - `corsheaders.middleware.CorsMiddleware`
  - `django.middleware.security.SecurityMiddleware`
  - `django.contrib.sessions.middleware.SessionMiddleware`
  - `django.middleware.common.CommonMiddleware`
  - `django.middleware.csrf.CsrfViewMiddleware`
  - `django.contrib.auth.middleware.AuthenticationMiddleware`
  - `django.contrib.messages.middleware.MessageMiddleware`
  - `django.middleware.clickjacking.XFrameOptionsMiddleware`
- `ROOT_URLCONF`: `marketplace.urls`.
- `TEMPLATES`: DjangoTemplates, `DIRS=[BASE_DIR / "templates"]`, `APP_DIRS=True`, standard debug/request/auth/messages context processors.
- `LOGIN_URL`: `/dashboard/admin/login/`.
- `WSGI_APPLICATION`: `marketplace.wsgi.application`.
- `DATABASES`: SQLite at `BASE_DIR / "db.sqlite3"`.
- `AUTH_PASSWORD_VALIDATORS`: standard four Django validators.
- `LANGUAGE_CODE`: `en-us`.
- `TIME_ZONE`: `Africa/Addis_Ababa`.
- `USE_I18N`: `True`.
- `USE_TZ`: `True`.
- `STATIC_URL`: `static/`.
- `STATIC_ROOT`: `BASE_DIR / "staticfiles"`.
- `MEDIA_URL`: `media/`.
- `MEDIA_ROOT`: `BASE_DIR / "media"`.
- `DEFAULT_AUTO_FIELD`: `django.db.models.BigAutoField`.
- `REST_FRAMEWORK`:
  - Auth: SessionAuthentication and TokenAuthentication.
  - Default permission: IsAuthenticated.
  - Pagination: PageNumberPagination, `PAGE_SIZE=10`.
  - SearchFilter and OrderingFilter.
  - Anon throttle `100/hour`, user throttle `1000/hour`.
  - Custom exception handler: `marketplace.api.exceptions.custom_exception_handler`.
- `CORS_ALLOWED_ORIGINS`: env CSV default `http://localhost:3000,http://localhost:8000`.
- `CORS_ALLOW_CREDENTIALS`: `True`.
- Telegram settings from env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_MINI_APP_URL`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_BOT_API_BASE_URL`, `BOT_WEBHOOK_SECRET`, `BOT_WEBHOOK_ASYNC`.
- `LOG_LEVEL`: env default `DEBUG`.
- `LOGGING`:
  - console StreamHandler
  - `logs/django.log` FileHandler at INFO
  - `logs/error.log` FileHandler at ERROR
  - `django` logger uses console + files, level `LOG_LEVEL`, propagate True.
  - `marketplace` logger uses console + files, level `LOG_LEVEL`, propagate False.
- `if not DEBUG:` block:
  - `SESSION_COOKIE_SECURE = True`
  - `CSRF_COOKIE_SECURE = True`
  - `SECURE_SSL_REDIRECT = True`

Missing production settings:

- `CSRF_TRUSTED_ORIGINS` is not defined.
- `SECURE_PROXY_SSL_HEADER` is not defined. This can cause redirect loops behind cPanel/Passenger proxies.
- `SECURE_HSTS_SECONDS` is not defined.
- `STATICFILES_DIRS` is not needed currently because `static/` is empty.
- No WhiteNoise middleware/storage.
- No production email backend.
- No MySQL database config.

### URLs Full Analysis

Main `marketplace/urls.py`:

- `/` -> Mini App landing page.
- `/favicon.ico` -> 204 empty favicon response.
- `/admin/` -> Django admin.
- `/dashboard/admin/login/` -> Django LoginView using `templates/adminpanel/login.html`.
- `/dashboard/admin/logout/` -> Django LogoutView.
- `/dashboard/admin/` -> admin dashboard.
- `/dashboard/admin/contact/<int:contact_request_id>/<str:action>/` -> dashboard contact action.
- `/dashboard/admin/service/<int:service_id>/<str:action>/` -> dashboard service action.
- `/api/health/` -> `health.urls`.
- `/api/bot/` -> `bot.urls`; webhook is `/api/bot/webhook/`.
- `/api/auth/telegram/` -> Mini App auth.
- `/api/me/` -> current Telegram user.
- `/api/profile/`, `/api/profile/location/`, `/api/profile/customer-location/`, `/api/profile/visibility/`.
- `/api/service/`, `/api/service/me/`, `/api/service/me/update/`, `/api/service/me/delete/`.
- `/api/service/prices/`, `/api/service/photos/`, `/api/service/photos/<photo_id>/`, `/api/service/photo/<photo_id>/`.
- `/api/discovery/swipe/`, `/api/discovery/grid/`.
- `/api/swipe/like/`, `/api/swipe/dislike/`, `/api/swipe/save/`, `/api/swipe/save/<service_id>/`, `/api/swipe/saved/`.
- `/api/contact-request/`, `/api/contact-request/status/`.
- Admin APIs for pending services/contacts, approvals/rejections, settings, provider badges, service admin visibility, reminders, timeouts, location updates, photo changes, surveys, advertisements.
- Nested app includes under `/api/accounts/`, `/api/services/`, `/api/swipes/`, `/api/matching/`, `/api/approvals/`, `/api/moderation/`, `/api/verification/`, `/api/miniapp/`, `/api/adminpanel/`.
- Static/media debug-only URL: `if settings.DEBUG: urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)`.
- No `debug_toolbar` URLs.
- No `handler400`, `handler403`, `handler404`, `handler500`.

App-level URL highlights:

- `bot/urls.py`: `webhook/`.
- `services/urls.py`: `categories/`, `category-avg-price/`, service CRUD, prices, photos, photo proxy.
- `matching/urls.py`: `discovery/swipe/`, `discovery/grid/`.
- `swipes/urls.py`: like/dislike/save/unsave/saved.
- `approvals/urls.py`: contact request create/status.
- `miniapp/urls.py`: landing and route check.
- `adminpanel/urls.py`: limited nested admin API routes; the main project URL file exposes the full admin API set.

### Models / Database Schema Summary

Project models:

- `accounts.TelegramUser`
  - Telegram identity: `telegram_id`, `telegram_username`, `first_name`, `last_name`
  - Contact/role: `phone_number`, `secondary_phone_number`, `role`
  - Trust/control: `is_verified`, `is_banned`, `admin_tested_badge`
  - Policy: `policy_accepted_at`, `policy_version`, `policy_failed_attempts`, `policy_blocked_until`
  - Location/activity: `city`, customer GPS fields, `customer_location_updated_at`, `last_interaction_at`
  - Counters: `likes_count`
  - Methods validate GPS within Ethiopia and derive city from `CityLocation`.

- `services.CityLocation`
  - `name`
  - polygon/bounds coordinates: top/bottom left/right x/y fields
  - class method maps GPS coordinate to city.

- `services.ServiceCategory`
  - `name`, `active`, timestamps.

- `services.ServiceProfile`
  - one-to-one `provider`
  - category, title, description
  - GPS/city location and `location_source`
  - `visibility_status`, `approval_status`, approval fields
  - moderation/performance: `admin_forced_hidden`, `denial_count`, `penalty_until`, `penalty_count`, `prior_penalty_count`, `likes_count`, `rejection_reason`, `location_update_requested_at`
  - helpers for discoverability, prices, photo counts.

- `services.ServicePrice`
  - service FK, `price_type` (`half_day`, `full_day`, `night`), `amount`.
  - unique `(service, price_type)`.

- `services.ServicePhoto`
  - service FK, `telegram_file_id`, `order_index`, `created_at`.
  - no local image field; maximum 3 photos enforced.

- `services.PhotoChangeRequest`
  - service FK, `new_file_id`, `order_index`, `status`, timestamps.

- `services.ProviderDenialLog`
  - service FK, reason, optional contact request FK, created timestamp.

- `swipes.SwipeHistory`
  - customer FK, service FK, `swipe_status`, `created_at`, `reset_at`.
  - DEBUG behavior: reset is immediate in DEBUG, one day in production.

- `swipes.SavedServiceRequest`
  - customer FK, service FK, `created_at`.
  - unique `(customer, service)`.

- `approvals.ContactRequest`
  - customer FK, provider FK, optional service FK, status, approval fields, created timestamp.

- `approvals.AdminSettings`
  - singleton settings row with `auto_approve_requests`, `reset_days`, `default_radius`.

- `approvals.CustomerSurvey`
  - one-to-one contact request, sent/responded timestamps, yes/no response, no reason.

- `bot.BotRegistrationSession`
  - `telegram_user_id`, `chat_id`, state, temporary city, JSON `data`, timestamps.

- `moderation.Report`
  - reporter FK, reported user FK, reason, status, created timestamp.

- `verification.VerifiedBadge`
  - one-to-one service, badge type.

- `adminpanel`, `health`, `matching`, `miniapp` have no real project models beyond placeholder files.

### Views / Bot / File Logic Summary

- Mini App landing: `miniapp/views.py` renders `templates/miniapp/app.html` and injects `TELEGRAM_BOT_USERNAME`.
- Mini App auth: `accounts/views.py::telegram_auth` validates Telegram `initData` through `miniapp/auth.py`, creates/updates `TelegramUser`, maps it to a Django `User`, and returns DRF token auth.
- Telegram webhook: `bot/views.py::telegram_webhook` is CSRF-exempt, POST-only, secret-header protected, decodes JSON, dispatches through `bot/dispatcher.py`.
- Bot dispatching: `bot/dispatcher.py` uses `ThreadPoolExecutor(max_workers=4)` when `BOT_WEBHOOK_ASYNC=True`.
- Bot API calls: `bot/services.py` uses `requests.Session`, timeouts, retry-disabled adapters, and forces IPv4 through `bot/networking.py`.
- Service photo proxy: `services/views.py::service_photo_proxy` fetches Telegram file bytes and returns them with `Cache-Control: public, max-age=86400`.
- No project code uses `print()`.
- Logging is through `logger.info`, `logger.warning`, `logger.exception`; logs go to `logs/django.log` and `logs/error.log`.
- Production caveat: in-process background threads can be interrupted if Passenger recycles workers. For higher reliability on shared hosting, set `BOT_WEBHOOK_ASYNC=False`, or move notifications to a real queue later.

### Custom Management Commands

- `python manage.py bot_webhook set|delete|status`
  - Uses `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_URL`, `BOT_WEBHOOK_SECRET`.
  - This is the preferred project-specific way to manage Telegram webhook.

- `python manage.py seed_demo_services`
  - Seeds local demo data; not for production unless you intentionally want demo providers.

- `python manage.py clear_data`
  - Deletes all project model data.
  - SQLite-specific: uses `PRAGMA foreign_keys` and `DELETE FROM sqlite_sequence`.
  - Do not run in production, and do not use after switching to MySQL without rewriting it.

### Static, Media, And Templates

- `templates/miniapp/app.html`: full Telegram Mini App UI, inline CSS/JS.
- `templates/adminpanel/dashboard.html`: admin dashboard.
- `templates/adminpanel/login.html`: admin login.
- `templates/adminpanel/forbidden.html`: admin 403 page for dashboard access.
- `templates/adminpanel/partials/*.html`: admin cards.
- No global `templates/400.html`, `403.html`, `404.html`, `500.html`.
- No symlinks/reparse points found in project static/media paths.

### Other Critical Files Found / Not Found

- `.htaccess`: not present in the local repo; cPanel will need one in `public_html`.
- `Dockerfile`: not present; this is not currently containerized.
- `docker-compose.yml`: not present.
- `Makefile`: not present.
- `requirements.txt`: not present; must be created before cPanel deployment.
- `passenger_wsgi.py`: not present; must be created for cPanel Passenger.
- Shell scripts found:
  - `a.sh`: local Cloudflare Tunnel helper for `http://localhost:8000`.
  - `b.sh`: local `python manage.py bot_webhook set/status` helper.
  - `c.sh`: local `python manage.py runserver` helper.
  - `start.sh`: stale local runserver helper pointing to `personal proj`, not `personalV1`.
- README/developer notes:
  - `README.md` says this is Django 4.2.11 + DRF + SQLite + Telegram bot placeholders + Mini App placeholders.
  - `COMMANDS.md` lists local activation, migration, superuser, runserver, health, and pytest commands.
  - `SYSTEM_STATE.md` says the recreated foundation includes SQLite, DRF, CORS, logging, environment variables, and health endpoint.

### DEBUG Mode Dependencies

Items in code that check `settings.DEBUG`:

- `marketplace/settings.py:11`: `DEBUG = config("DEBUG", default=True, cast=bool)`.
- `marketplace/settings.py:13`: `ALLOWED_HOSTS = ["*"] if DEBUG else ENV_ALLOWED_HOSTS`.
- `marketplace/settings.py:184`: `if not DEBUG:` enables secure cookies and SSL redirect.
- `marketplace/urls.py:199`: media serving via `static(settings.MEDIA_URL, ...)` only in DEBUG.
- `matching/views.py:288`: when DEBUG, `recently_seen_service_ids` is empty, so discovery does not suppress recently swiped services.
- `swipes/models.py:79`: when DEBUG, `SwipeHistory.reset_at = timezone.now()`; when production, reset is `timezone.now() + timedelta(days=1)`.

### Potential Issues When DEBUG = False

- `ALLOWED_HOSTS` becomes strict and defaults to only `localhost,127.0.0.1` if env is not set.
- Django stops adding development media URL serving.
- `SECURE_SSL_REDIRECT=True` activates. Behind cPanel/Passenger this may cause a redirect loop without `SECURE_PROXY_SSL_HEADER`.
- `SESSION_COOKIE_SECURE=True` and `CSRF_COOKIE_SECURE=True` require HTTPS.
- `CSRF_TRUSTED_ORIGINS` is missing and should be added for admin forms and cross-origin HTTPS flows.
- Static files are not served by Django; Apache/cPanel must serve `/static/`, or you must add WhiteNoise.
- Discovery results change because recently swiped services are filtered in production.
- Swipe history lasts a day instead of immediately resetting.
- Mini App auth requires valid Telegram initData and a correct bot token.
- `TELEGRAM_MINI_APP_URL` must be your real HTTPS root URL, not localhost.
- `BOT_WEBHOOK_SECRET` must be set; webhook returns 500 if missing and 401 if header mismatch.
- SQLite can lock under webhook/admin traffic. MySQL is strongly recommended.
- `health/views.py` currently returns `"database": "sqlite"` hardcoded, even after MySQL migration unless you update it.

### Security Implications

- `SECRET_KEY`: env variable with unsafe default. Must be generated and set in cPanel.
- Database credentials: not currently in settings. Add cPanel MySQL env variables.
- API keys/secrets:
  - `TELEGRAM_BOT_TOKEN`
  - `BOT_WEBHOOK_SECRET`
  - `TELEGRAM_WEBHOOK_URL`
  - `TELEGRAM_MINI_APP_URL`
- `.env` is ignored by Git but must not be uploaded into `public_html`.
- Local `db.sqlite3` is ignored but exists; do not expose it publicly.
- Local `logs/*.log` may contain stack traces and operational data; do not upload old logs to public web root.
- `DEBUG=True` allows all hosts because `ALLOWED_HOSTS=["*"]`; never run production with DEBUG=True.

## PRE-DEPLOYMENT TASKS CHECKLIST

### Settings.py Modifications Required

- [ ] Change `DEBUG` production default to `False`.
- [ ] Set `ALLOWED_HOSTS=<YOUR_DOMAIN>,www.<YOUR_DOMAIN>`.
- [ ] Configure MySQL database settings; current SQLite config is development-only.
- [ ] Change `STATIC_URL` and `MEDIA_URL` to leading-slash paths: `/static/`, `/media/`.
- [ ] Set `STATIC_ROOT` to `/home/<CPANEL_USER>/public_html/static`.
- [ ] Set `MEDIA_ROOT` to `/home/<CPANEL_USER>/public_html/media`.
- [ ] Add `CSRF_TRUSTED_ORIGINS=https://<YOUR_DOMAIN>,https://www.<YOUR_DOMAIN>`.
- [ ] Keep `SESSION_COOKIE_SECURE=True` and `CSRF_COOKIE_SECURE=True` in production.
- [ ] Add `SECURE_PROXY_SSL_HEADER` to avoid cPanel SSL redirect loops.
- [ ] Decide `SECURE_SSL_REDIRECT=True` only after SSL is active.
- [ ] Add `SECURE_HSTS_SECONDS` after confirming HTTPS is stable.
- [ ] Set production `LOG_LEVEL=INFO`.
- [ ] Optionally update `health/views.py` to report the actual DB backend.

### Environment Variables To Create In cPanel

- [ ] `SECRET_KEY`
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS=<YOUR_DOMAIN>,www.<YOUR_DOMAIN>`
- [ ] `CSRF_TRUSTED_ORIGINS=https://<YOUR_DOMAIN>,https://www.<YOUR_DOMAIN>`
- [ ] `CORS_ALLOWED_ORIGINS=https://<YOUR_DOMAIN>,https://www.<YOUR_DOMAIN>`
- [ ] `DB_NAME=<CPANEL_USER>_<DB_NAME>`
- [ ] `DB_USER=<CPANEL_USER>_<DB_USER>`
- [ ] `DB_PASSWORD=<DB_PASSWORD>`
- [ ] `DB_HOST=localhost`
- [ ] `DB_PORT=3306`
- [ ] `TELEGRAM_BOT_TOKEN=<BOT_TOKEN>`
- [ ] `TELEGRAM_BOT_USERNAME=<BOT_USERNAME_WITHOUT_OR_WITH_@>`
- [ ] `TELEGRAM_MINI_APP_URL=https://<YOUR_DOMAIN>/`
- [ ] `TELEGRAM_WEBHOOK_URL=https://<YOUR_DOMAIN>/api/bot/webhook/`
- [ ] `BOT_WEBHOOK_SECRET=<BOT_SECRET>`
- [ ] `BOT_WEBHOOK_ASYNC=False` for safer shared-hosting behavior, or `True` if tested.
- [ ] `LOG_LEVEL=INFO`
- [ ] `STATIC_ROOT=/home/<CPANEL_USER>/public_html/static`
- [ ] `MEDIA_ROOT=/home/<CPANEL_USER>/public_html/media`

### Error Pages To Create

- [ ] `templates/400.html`
- [ ] `templates/403.html`
- [ ] `templates/404.html`
- [ ] `templates/500.html`

### Static/Media Setup

- [ ] Create `/home/<CPANEL_USER>/public_html/static`.
- [ ] Create `/home/<CPANEL_USER>/public_html/media`.
- [ ] Run `collectstatic`.
- [ ] Confirm `/static/admin/css/base.css` loads from the domain.

### Webhook Setup

- [ ] Confirm SSL works on `https://<YOUR_DOMAIN>/`.
- [ ] Set `TELEGRAM_WEBHOOK_URL=https://<YOUR_DOMAIN>/api/bot/webhook/`.
- [ ] Run `python manage.py bot_webhook set`.
- [ ] Verify with `python manage.py bot_webhook status`.

## What Happens When DEBUG = False?

### 1. Static Files Behavior Change

In development, Django can serve static/media helpers. In production, Django expects the web server to serve static files.

For this project:

- `static/` is empty.
- `collectstatic` collects 160 Django admin/DRF files into `STATIC_ROOT`.
- `STATIC_ROOT` currently points to `BASE_DIR / "staticfiles"`, which is not public on cPanel.

Production setup:

1. Set `STATIC_ROOT=/home/<CPANEL_USER>/public_html/static`.
2. Run:

```bash
python manage.py collectstatic --noinput
```

3. Test:

```bash
curl -I https://<YOUR_DOMAIN>/static/admin/css/base.css
```

Expected output: `HTTP/2 200` or `HTTP/1.1 200 OK`.

### 2. Media Files Behavior Change

`marketplace/urls.py` only serves media when `settings.DEBUG` is true:

```python
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

With `DEBUG=False`, Django will not serve `/media/`. This project currently stores provider photos as Telegram file IDs and serves them through `/api/service/photo/<photo_id>/`, so existing service photos do not rely on local media files. Still, create `/home/<CPANEL_USER>/public_html/media` for future local files.

### 3. Error Handling Change

With `DEBUG=False`, Django no longer shows detailed tracebacks in the browser. Users will see generic pages unless you create:

- `templates/400.html`
- `templates/403.html`
- `templates/404.html`
- `templates/500.html`

Test a 404 after deployment:

```bash
curl -I https://<YOUR_DOMAIN>/this-url-should-not-exist/
```

Expected: `404`, not a traceback.

### 4. Security Settings Activation

Current production block:

```python
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
```

Effects:

- Sessions and CSRF cookies only work over HTTPS.
- HTTP requests redirect to HTTPS.
- If cPanel passes HTTPS through a proxy, add `SECURE_PROXY_SSL_HEADER` or redirects can loop.
- `ALLOWED_HOSTS` switches from `["*"]` to env-defined hosts.

### 5. Database Behavior Change

If you follow this guide, production moves from SQLite to MySQL. Effects:

- Better concurrency for Telegram webhooks and admin batch endpoints.
- No SQLite `database is locked` failures under normal traffic.
- `clear_data` management command becomes unsafe because it uses SQLite-only SQL.
- You must run migrations on MySQL before setting the webhook.

### 6. Debug-Only Code Paths

- `matching/views.py`: recently swiped services are ignored in DEBUG but filtered in production.
- `swipes/models.py`: swipe reset is immediate in DEBUG but one day in production.
- `marketplace/urls.py`: media helper route only exists in DEBUG.
- `marketplace/settings.py`: secure cookies and SSL redirect only activate when not DEBUG.

### 7. Performance Differences

Production discovery evaluates ranking, distance, recent requests, prices, and swipe history. MySQL indexes from migrations are important. Avoid running production on SQLite because webhook and batch traffic can contend for writes.

### 8. Logging Behavior Change

Console logs may not be visible in cPanel Passenger. File logging is already configured:

- `<APP_ROOT>/logs/django.log`
- `<APP_ROOT>/logs/error.log`

Ensure `<APP_ROOT>/logs` exists and is writable by the cPanel Python app.

### 9. Environment Variable Requirements

Development defaults are not safe:

- `SECRET_KEY` default is insecure.
- `DEBUG` default is true.
- `TELEGRAM_MINI_APP_URL` can fall back to localhost.
- `BOT_WEBHOOK_SECRET` default is empty and makes the webhook return 500.

Set every variable listed in the checklist before enabling the Telegram webhook.

## Pre-Deployment Verification Checklist

- [ ] All static files are verified locally with `python manage.py collectstatic --dry-run --noinput`.
- [ ] All migrations are created and applied locally.
- [ ] `python manage.py check` passes locally.
- [ ] `DEBUG=False` is tested locally with `ALLOWED_HOSTS`.
- [ ] `python manage.py check --deploy` warnings are understood.
- [ ] `templates/400.html`, `403.html`, `404.html`, `500.html` exist.
- [ ] `ALLOWED_HOSTS` includes `<YOUR_DOMAIN>` and `www.<YOUR_DOMAIN>`.
- [ ] `SECRET_KEY` is stored in environment variable.
- [ ] Telegram token and webhook secret are stored in environment variables.
- [ ] Database is switched from SQLite to MySQL.
- [ ] `STATIC_ROOT` and `MEDIA_ROOT` are cPanel production paths.
- [ ] `requirements.txt` is created.
- [ ] `passenger_wsgi.py` is created.
- [ ] Webhook URL is prepared with HTTPS.
- [ ] `.env` values are documented but `.env` is not inside `public_html`.
- [ ] Local `logs/`, `.pytest_cache/`, `venv/`, and `db.sqlite3` are not uploaded as public files.

## PART 1: Pre-Deployment Code Configuration

### 1.1 Update settings.py For Production

Edit `marketplace/settings.py`.

#### SECRET_KEY and DEBUG

Current code:

```python
SECRET_KEY = config("SECRET_KEY", default="django-insecure-dev-key")
DEBUG = config("DEBUG", default=True, cast=bool)
ENV_ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
ALLOWED_HOSTS = ["*"] if DEBUG else ENV_ALLOWED_HOSTS
```

Production code:

```python
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ENV_ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="", cast=Csv())
ALLOWED_HOSTS = ["localhost", "127.0.0.1"] if DEBUG else ENV_ALLOWED_HOSTS
```

Why:

- Production must fail fast if `SECRET_KEY` is missing.
- Production must not default to `DEBUG=True`.
- `ALLOWED_HOSTS=["*"]` is acceptable only while developing locally.

#### Database

Current code:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

Production code using `mysqlclient`:

```python
DB_ENGINE = config("DB_ENGINE", default="django.db.backends.sqlite3")

if DB_ENGINE == "django.db.backends.mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
```

Why:

- cPanel production should use MySQL/MariaDB.
- The existing `.env.example` mentions `DATABASE_URL`, but the code does not read it.
- This keeps local SQLite available while enabling MySQL by setting `DB_ENGINE=django.db.backends.mysql`.

If `mysqlclient` cannot install, use PyMySQL. Add this near the top of `marketplace/__init__.py`:

```python
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
```

Then use `PyMySQL==1.1.1` in `requirements.txt` instead of `mysqlclient`.

#### Static And Media

Current code:

```python
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
```

Production code:

```python
STATIC_URL = "/static/"
STATIC_ROOT = Path(config("STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))
```

Why:

- Leading slashes avoid relative URL surprises.
- cPanel can set `STATIC_ROOT=/home/<CPANEL_USER>/public_html/static`.
- cPanel can set `MEDIA_ROOT=/home/<CPANEL_USER>/public_html/media`.

#### CORS And CSRF

Current code:

```python
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:8000",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
```

Production code:

```python
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="",
    cast=Csv(),
)
```

Why:

- Current defaults are localhost-only.
- Admin login and HTTPS form posts should trust your real domain.

#### SSL And Secure Proxy

Current code:

```python
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
```

Production code:

```python
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = config("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool)
    SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)
```

Why:

- cPanel often terminates SSL before Passenger; `SECURE_PROXY_SSL_HEADER` prevents redirect loops.
- Start HSTS at `0`; increase only after confirming HTTPS is stable.

#### Logging

Current code creates `logs/` and writes file logs there. Keep it, but set:

```env
LOG_LEVEL=INFO
```

Why:

- DEBUG logs can grow quickly on shared hosting.
- File logging is already project-specific and useful for webhook troubleshooting.

#### Health Endpoint Optional Fix

Current `health/views.py` hardcodes:

```python
"database": "sqlite",
```

Production code:

```python
from django.db import connection

"database": connection.vendor,
```

Why:

- After MySQL migration, `/api/health/` should not claim SQLite.

### 1.2 Create Production Error Pages

Create these files in `templates/`.

`templates/404.html`:

```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Page Not Found</title></head>
<body style="font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0;background:#f6f8fb;color:#172033">
  <main style="max-width:520px;padding:32px;text-align:center">
    <h1>Page not found</h1>
    <p>The page you requested does not exist.</p>
    <a href="/" style="color:#0f766e">Open Marketplace</a>
  </main>
</body>
</html>
```

Create the same structure for:

- `400.html`: title `Bad Request`, text `The request could not be processed.`
- `403.html`: title `Forbidden`, text `You do not have permission to view this page.`
- `500.html`: title `Server Error`, text `Something went wrong. Please try again later.`

Why:

- With `DEBUG=False`, Django will not show technical tracebacks.

### 1.3 Create Requirements.txt

There is currently no `requirements.txt`. Create one at project root.

Recommended production `requirements.txt`:

```txt
Django==4.2.11
djangorestframework==3.14.0
django-cors-headers==4.3.1
python-decouple==3.8
python-telegram-bot==21.0
requests==2.31.0
Pillow==10.1.0
mysqlclient==2.2.4
asgiref==3.11.1
sqlparse==0.5.5
tzdata==2026.2
```

If `mysqlclient` fails on cPanel, replace it with:

```txt
PyMySQL==1.1.1
```

What this does:

- Installs Django, DRF, CORS middleware, env loading, Telegram support, HTTP calls, and MySQL support.

Expected output:

- `Successfully installed ...`

Do not include `pytest`, `coverage`, or `pytest-django` in production unless your cPanel has enough disk quota and you intentionally run tests there.

### 1.4 Create passenger_wsgi.py

There is currently no `passenger_wsgi.py`. Create it in the project root:

```python
import os
import sys

PROJECT_ROOT = os.path.dirname(__file__)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "marketplace.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
```

Why:

- cPanel Passenger looks for a startup file. `marketplace/wsgi.py` exists, but cPanel Python App commonly expects `passenger_wsgi.py` at app root.

### 1.5 Generate New SECRET_KEY

Run locally or in cPanel terminal:

```bash
python - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
```

What it does:

- Generates a strong Django secret key.

Expected output:

- One long random string. Put it in cPanel environment variable `SECRET_KEY`.

## PART 2: cPanel Database Setup

### 2.1 MySQL Database Creation

In cPanel:

1. Open `MySQL Databases`.
2. Create database: `<CPANEL_USER>_marketplace`.
3. Create user: `<CPANEL_USER>_market`.
4. Generate a strong password and save it securely.

Project-specific environment values:

```env
DB_ENGINE=django.db.backends.mysql
DB_NAME=<CPANEL_USER>_marketplace
DB_USER=<CPANEL_USER>_market
DB_PASSWORD=<YOUR_DB_PASSWORD>
DB_HOST=localhost
DB_PORT=3306
```

### 2.2 Database User And Privileges

In cPanel MySQL Databases:

1. Add user `<CPANEL_USER>_market` to database `<CPANEL_USER>_marketplace`.
2. Grant `ALL PRIVILEGES`.
3. Save changes.

Why:

- Django migrations need CREATE/ALTER/INDEX permissions.

### 2.3 SQLite To MySQL Data Transfer

If the local `db.sqlite3` has real data you need:

On local machine before switching settings:

```bash
python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.Permission --indent 2 > data-export.json
```

What it does:

- Exports data from SQLite into JSON.

After deploying and migrating MySQL:

```bash
python manage.py loaddata data-export.json
```

What to expect:

- Django prints installed object count.

If you do not need local data, skip dump/load and only run migrations on MySQL.

## PART 3: cPanel Python App Setup

### 3.1 Setup Python Application

In cPanel `Setup Python App`:

- Python version: `3.12` if available; otherwise `3.11`.
- Application root: `repositories/personalV1`.
- Application URL: `/` if this domain is dedicated to this app.
- Application startup file: `passenger_wsgi.py`.
- Application entry point: `application`.

Expected cPanel app root:

```text
/home/<CPANEL_USER>/repositories/personalV1
```

Expected virtualenv:

```text
/home/<CPANEL_USER>/virtualenv/repositories/personalV1/3.12
```

### 3.2 Configure Environment Variables

Add these in cPanel Setup Python App environment variables:

```env
SECRET_KEY=<GENERATED_SECRET_KEY>
DEBUG=False
ALLOWED_HOSTS=<YOUR_DOMAIN>,www.<YOUR_DOMAIN>
CSRF_TRUSTED_ORIGINS=https://<YOUR_DOMAIN>,https://www.<YOUR_DOMAIN>
CORS_ALLOWED_ORIGINS=https://<YOUR_DOMAIN>,https://www.<YOUR_DOMAIN>

DB_ENGINE=django.db.backends.mysql
DB_NAME=<CPANEL_USER>_marketplace
DB_USER=<CPANEL_USER>_market
DB_PASSWORD=<YOUR_DB_PASSWORD>
DB_HOST=localhost
DB_PORT=3306

TELEGRAM_BOT_TOKEN=<BOT_TOKEN>
TELEGRAM_BOT_USERNAME=<BOT_USERNAME>
TELEGRAM_MINI_APP_URL=https://<YOUR_DOMAIN>/
TELEGRAM_WEBHOOK_URL=https://<YOUR_DOMAIN>/api/bot/webhook/
TELEGRAM_BOT_API_BASE_URL=https://api.telegram.org
BOT_WEBHOOK_SECRET=<BOT_SECRET>
BOT_WEBHOOK_ASYNC=False

LOG_LEVEL=INFO
STATIC_ROOT=/home/<CPANEL_USER>/public_html/static
MEDIA_ROOT=/home/<CPANEL_USER>/public_html/media
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=0
```

Why `BOT_WEBHOOK_ASYNC=False` first:

- Shared-hosting Passenger workers can be recycled. Synchronous webhook handling is slower but safer until the site is proven stable.

## PART 4: Upload Files To cPanel

### 4.1 Directory Structure

Recommended production structure:

```text
/home/<CPANEL_USER>/
  repositories/
    personalV1/
      accounts/
      adminpanel/
      approvals/
      bot/
      health/
      marketplace/
      matching/
      miniapp/
      moderation/
      services/
      swipes/
      templates/
      tests/
      verification/
      manage.py
      passenger_wsgi.py
      requirements.txt
      logs/
  public_html/
    static/
    media/
```

Do not upload these to public web paths:

- `.env`
- `db.sqlite3`
- `venv/`
- `.pytest_cache/`
- `.git/`
- old `logs/*.log`

### 4.2 Upload Via FTP/File Manager

Upload project code to:

```text
/home/<CPANEL_USER>/repositories/personalV1
```

Upload includes:

- all Django app directories
- `marketplace/`
- `templates/`
- `manage.py`
- `requirements.txt`
- `passenger_wsgi.py`

Upload excludes:

- local virtualenv
- SQLite database unless you intentionally want to import data separately
- old local logs

### 4.3 Set Permissions

In cPanel terminal:

```bash
cd /home/<CPANEL_USER>/repositories/personalV1
mkdir -p logs
mkdir -p /home/<CPANEL_USER>/public_html/static
mkdir -p /home/<CPANEL_USER>/public_html/media
chmod 755 /home/<CPANEL_USER>/repositories/personalV1
chmod 755 /home/<CPANEL_USER>/public_html/static
chmod 755 /home/<CPANEL_USER>/public_html/media
chmod 755 logs
```

What it does:

- Creates required writable directories.

Expected output:

- No output if successful.

## PART 5: Install Dependencies And Migrate Database

### 5.1 Access Terminal / Virtual Environment

In cPanel Terminal:

```bash
source /home/<CPANEL_USER>/virtualenv/repositories/personalV1/3.12/bin/activate
cd /home/<CPANEL_USER>/repositories/personalV1
```

If your cPanel uses Python 3.11, adjust the path:

```bash
source /home/<CPANEL_USER>/virtualenv/repositories/personalV1/3.11/bin/activate
```

What it does:

- Activates the cPanel-created Python environment.

Expected output:

- Your shell prompt usually shows the virtualenv name.

### 5.2 Install Requirements

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

What it does:

- Installs this project's Python runtime dependencies.

Expected output:

- `Successfully installed ...`

If `mysqlclient` fails:

1. Edit `requirements.txt`: remove `mysqlclient`, add `PyMySQL==1.1.1`.
2. Add the PyMySQL snippet to `marketplace/__init__.py`.
3. Re-run:

```bash
python -m pip install -r requirements.txt
```

### 5.3 Run Migrations

```bash
python manage.py check
python manage.py migrate
```

What it does:

- Verifies configuration.
- Creates all database tables in MySQL.

Expected output:

- `System check identified no issues`
- migration lines ending with `OK`

Important migrations include:

- `accounts.0001` to `0004`
- `services.0001` to `0009_seed_city_locations`
- `approvals.0001` to `0004`
- `bot.0001` to `0004`
- `swipes.0001` to `0002`
- `moderation.0001`
- `verification.0001`

### 5.4 Create Admin User

```bash
python manage.py createsuperuser
```

What it does:

- Creates a Django admin/staff account for `/admin/` and `/dashboard/admin/`.

Expected output:

- Prompts for username, email, password.

### 5.5 Collect Static Files

```bash
python manage.py collectstatic --noinput
```

What it does:

- Copies Django admin and DRF static assets into `/home/<CPANEL_USER>/public_html/static`.

Expected output:

- Around `160 static files copied`.

### 5.6 Optional Data Import

If you exported local data:

```bash
python manage.py loaddata data-export.json
```

Expected output:

- `Installed X object(s) from 1 fixture(s)`.

## PART 6: Configure .htaccess For Production

### 6.1 Passenger .htaccess

cPanel usually generates this automatically. If you need to create or inspect it, place it in:

```text
/home/<CPANEL_USER>/public_html/.htaccess
```

Typical Passenger block:

```apache
PassengerAppRoot /home/<CPANEL_USER>/repositories/personalV1
PassengerBaseURI /
PassengerPython /home/<CPANEL_USER>/virtualenv/repositories/personalV1/3.12/bin/python
PassengerAppType wsgi
PassengerStartupFile passenger_wsgi.py
```

Adjust `PassengerPython` to the exact path cPanel displays.

### 6.2 Force HTTPS

Only add this after SSL works:

```apache
RewriteEngine On
RewriteCond %{HTTPS} !=on
RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
```

Why:

- Telegram Mini Apps and webhooks require HTTPS.

If you already use `SECURE_SSL_REDIRECT=True`, avoid duplicate/conflicting redirects. Use either Apache HTTPS redirect or Django redirect after confirming no loop.

### 6.3 Block Sensitive Files

Add:

```apache
<FilesMatch "^(\.env|db\.sqlite3|requirements\.txt|manage\.py|passenger_wsgi\.py)$">
    Require all denied
</FilesMatch>

<IfModule mod_rewrite.c>
RewriteEngine On
RewriteRule (^|/)(\.git|venv|logs|__pycache__|\.pytest_cache)(/|$) - [F,L]
</IfModule>
```

Why:

- Prevents accidental exposure if a sensitive file is copied into `public_html`.

### 6.4 Security Headers

Add:

```apache
<IfModule mod_headers.c>
Header always set X-Content-Type-Options "nosniff"
Header always set Referrer-Policy "same-origin"
Header always set X-Frame-Options "SAMEORIGIN"
Header always set Permissions-Policy "geolocation=(self), camera=(), microphone=()"
</IfModule>
```

Do not set a restrictive Content-Security-Policy until the Mini App and admin inline CSS/JS are refactored. Current templates contain inline CSS and JS.

## PART 7: Telegram Webhook Configuration

### 7.1 Test Application Is Running

```bash
curl -I https://<YOUR_DOMAIN>/
curl https://<YOUR_DOMAIN>/api/health/
```

Expected:

- Root returns `200`.
- Health returns JSON with `"success": true`.

Note: direct root browser testing is not the same as Telegram Mini App auth. The Mini App APIs require Telegram `initData`.

### 7.2 Set Webhook With Project Command

Make sure env contains:

```env
TELEGRAM_WEBHOOK_URL=https://<YOUR_DOMAIN>/api/bot/webhook/
BOT_WEBHOOK_SECRET=<BOT_SECRET>
TELEGRAM_BOT_TOKEN=<BOT_TOKEN>
```

Run:

```bash
python manage.py bot_webhook set
```

What it does:

- Calls Telegram `setWebhook`.
- Sends the webhook URL.
- Sends `secret_token`.
- Drops pending updates.
- Allows `message`, `edited_message`, `callback_query`.

Expected output:

```text
Telegram webhook set successfully.
Webhook URL: https://<YOUR_DOMAIN>/api/bot/webhook/
```

### 7.3 Raw Curl Alternative

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://<YOUR_DOMAIN>/api/bot/webhook/" \
  -d "secret_token=<BOT_SECRET>" \
  -d "drop_pending_updates=true" \
  -d 'allowed_updates=["message","edited_message","callback_query"]'
```

### 7.4 Verify Webhook

Project command:

```bash
python manage.py bot_webhook status
```

Raw curl:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

Expected:

- `url` equals `https://<YOUR_DOMAIN>/api/bot/webhook/`.
- `pending_update_count` is reasonable.
- `last_error_message` is empty or old.

## PART 8: Configure Cron Jobs

This project has no Celery or APScheduler. Use cPanel Cron Jobs to call authenticated admin endpoints.

### 8.1 Create Admin Token

In Django shell:

```bash
python manage.py shell
```

Then:

```python
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
u = User.objects.get(username="<YOUR_SUPERUSER_USERNAME>")
token, _ = Token.objects.get_or_create(user=u)
print(token.key)
```

Save the printed value as `<ADMIN_TOKEN>`.

### 8.2 Cron: Process 24h Provider Timeouts

Run hourly:

```bash
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/process-timeouts/" \
  -H "Authorization: Token <ADMIN_TOKEN>" \
  -H "Content-Type: application/json"
```

What it does:

- Converts provider-pending contact requests older than 24 hours to provider rejected.
- Increments denial count and may apply penalties.

### 8.3 Cron: Monthly Location Update Requests

Run daily or weekly:

```bash
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/request-location-updates/" \
  -H "Authorization: Token <ADMIN_TOKEN>" \
  -H "Content-Type: application/json"
```

### 8.4 Cron: Send Surveys

Run daily:

```bash
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/send-surveys/" \
  -H "Authorization: Token <ADMIN_TOKEN>" \
  -H "Content-Type: application/json"
```

### 8.5 Cron: Registration Reminders

Run daily around 09:00 Africa/Addis_Ababa:

```bash
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/send-mass-reminders/" \
  -H "Authorization: Token <ADMIN_TOKEN>" \
  -H "Content-Type: application/json"
```

### 8.6 Cron: Advertisement Broadcast

Use manually or on a controlled schedule:

```bash
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/send-advertisement/" \
  -H "Authorization: Token <ADMIN_TOKEN>" \
  -H "Content-Type: application/json"
```

Warning:

- This sends Telegram photos/messages to customers. Test with a small dataset before using in production.

## PART 9: Final Testing Protocol

### 9.1 Static Files Test

```bash
curl -I https://<YOUR_DOMAIN>/static/admin/css/base.css
```

Expected:

- `200 OK`.

### 9.2 Media Files Test

Because local media is empty, test the directory response:

```bash
curl -I https://<YOUR_DOMAIN>/media/
```

Expected:

- `403` or `404` is acceptable for directory listing.
- Do not expect a provider photo here; provider photos use `/api/service/photo/<photo_id>/`.

### 9.3 Health Test

```bash
curl https://<YOUR_DOMAIN>/api/health/
```

Expected:

```json
{"success":true,"status":"ok","service":"telegram-service-marketplace","database":"sqlite"}
```

If you applied the optional health fix, expected database is `mysql`.

### 9.4 Admin Login Test

Open:

```text
https://<YOUR_DOMAIN>/dashboard/admin/login/
```

Expected:

- Admin login page loads.
- After login, `/dashboard/admin/` opens for staff/superuser or Telegram admin.

### 9.5 Webhook Secret Rejection Test

```bash
curl -i -X POST "https://<YOUR_DOMAIN>/api/bot/webhook/" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Expected:

- `401 Unauthorized`, because the secret header is missing.

### 9.6 Webhook Valid Header Smoke Test

```bash
curl -i -X POST "https://<YOUR_DOMAIN>/api/bot/webhook/" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: <BOT_SECRET>" \
  -d '{"update_id": 1}'
```

Expected:

- It should not return `401`.
- It may return a handled false/unsupported route response because this is not a full Telegram message.

### 9.7 Bot Command Test

In Telegram:

1. Open your bot.
2. Send `/start`.
3. Confirm the start menu appears.
4. Tap `Open Marketplace`.
5. Confirm the Mini App loads from `https://<YOUR_DOMAIN>/`.

### 9.8 Error Logs Check

Check:

```bash
tail -n 100 /home/<CPANEL_USER>/repositories/personalV1/logs/error.log
tail -n 100 /home/<CPANEL_USER>/repositories/personalV1/logs/django.log
```

Also check cPanel:

- Metrics -> Errors
- Setup Python App -> app logs if your host exposes them.

## PART 10: Troubleshooting Guide

### 10.1 500 Internal Server Error

Project-specific likely causes:

- Missing `SECRET_KEY`.
- Missing `TELEGRAM_BOT_TOKEN`.
- Missing `BOT_WEBHOOK_SECRET`.
- MySQL credentials wrong.
- `logs/` directory not writable.
- `passenger_wsgi.py` path wrong.

Commands:

```bash
python manage.py check
tail -n 100 logs/error.log
```

### 10.2 DisallowedHost

Symptom:

- Browser shows bad request.
- Logs mention invalid `HTTP_HOST`.

Fix:

```env
ALLOWED_HOSTS=<YOUR_DOMAIN>,www.<YOUR_DOMAIN>
```

Restart the Python app in cPanel.

### 10.3 Redirect Loop After DEBUG=False

Cause:

- `SECURE_SSL_REDIRECT=True` but Django does not know the original request is HTTPS behind cPanel proxy.

Fix in `settings.py`:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

If still looping, temporarily set:

```env
SECURE_SSL_REDIRECT=False
```

Then use Apache `.htaccess` HTTPS redirect instead.

### 10.4 Module Not Found Errors

Common examples:

- `No module named rest_framework`: requirements not installed.
- `No module named corsheaders`: requirements not installed.
- `No module named decouple`: `python-decouple` missing.
- `No module named MySQLdb`: `mysqlclient` missing.

Fix:

```bash
source /home/<CPANEL_USER>/virtualenv/repositories/personalV1/3.12/bin/activate
cd /home/<CPANEL_USER>/repositories/personalV1
python -m pip install -r requirements.txt
```

For MySQLdb:

- Install `mysqlclient`, or switch to `PyMySQL` as described above.

### 10.5 Static Files Not Loading

Symptoms:

- Django admin has no CSS.
- DRF browsable API has no CSS.

Fix:

```bash
python manage.py collectstatic --noinput
ls -la /home/<CPANEL_USER>/public_html/static/admin/css/base.css
curl -I https://<YOUR_DOMAIN>/static/admin/css/base.css
```

Also confirm:

```env
STATIC_ROOT=/home/<CPANEL_USER>/public_html/static
```

### 10.6 Media Files Not Loading

Current service photos do not use local media. They use:

```text
/api/service/photo/<photo_id>/
```

If that fails:

- Confirm `TELEGRAM_BOT_TOKEN` is correct.
- Confirm outbound HTTPS to `api.telegram.org` is allowed.
- Check `logs/error.log` for `event=service_photo_proxy_fetch_failed`.

If future local media files fail:

- Confirm files are under `/home/<CPANEL_USER>/public_html/media`.
- Confirm Apache can serve `/media/`.

### 10.7 Database Connection Errors

Symptoms:

- `Access denied for user`
- `Unknown database`
- `Can't connect to MySQL server`

Fix:

- Confirm cPanel database names include the `<CPANEL_USER>_` prefix.
- Confirm user is assigned to DB with `ALL PRIVILEGES`.
- Confirm env variables match exactly.
- Run:

```bash
python manage.py dbshell
```

### 10.8 SQLite Lock Errors

Symptoms:

- Logs show `sqlite3.OperationalError: database is locked`.
- Bot randomly fails during webhooks.

Fix:

- Move to MySQL. This project has concurrent webhook and admin batch behavior.

### 10.9 Webhook Not Working

Symptoms:

- Bot does not respond.
- Telegram `getWebhookInfo` shows last error.

Fix:

```bash
python manage.py bot_webhook status
python manage.py bot_webhook set
```

Check:

- `TELEGRAM_WEBHOOK_URL=https://<YOUR_DOMAIN>/api/bot/webhook/`
- `BOT_WEBHOOK_SECRET` exists.
- cPanel SSL certificate is valid.
- `/api/bot/webhook/` returns `401` without secret, not `404`.

### 10.10 Telegram Bot Not Responding

Likely causes:

- `TELEGRAM_BOT_TOKEN` wrong.
- `BOT_WEBHOOK_SECRET` mismatch between Telegram and Django.
- Passenger worker crashed.
- Outbound requests to `api.telegram.org` blocked by host.
- `BOT_WEBHOOK_ASYNC=True` background thread failed after response.

Fix:

```bash
tail -n 100 logs/error.log
python manage.py bot_webhook status
```

Set safer mode:

```env
BOT_WEBHOOK_ASYNC=False
```

Restart the Python app.

### 10.11 Mini App Shows Background But No Data

Project-specific causes:

- Direct browser testing lacks Telegram `initData`; `/api/auth/telegram/` will fail.
- `TELEGRAM_BOT_TOKEN` used for validation does not match the bot that opened the Mini App.
- `TELEGRAM_MINI_APP_URL` still points to localhost.
- JavaScript runtime error in `templates/miniapp/app.html`.

Fix:

- Open from Telegram bot button, not a normal browser tab.
- Set:

```env
TELEGRAM_MINI_APP_URL=https://<YOUR_DOMAIN>/
TELEGRAM_BOT_USERNAME=<BOT_USERNAME>
```

- Check browser console if testing outside Telegram.
- Check `/api/auth/telegram/` responses in Network tab.

### 10.12 Contact Request Or Discovery Says LOCATION_REQUIRED

This is expected. `matching/views.py` and `approvals/views.py` require customer GPS/city context. User must share location through the bot/Mini App flow.

### 10.13 Cron Endpoints Return Authentication Credentials Were Not Provided

Cause:

- Cron request did not include DRF token auth.

Fix:

```bash
curl -X POST "https://<YOUR_DOMAIN>/api/admin/process-timeouts/" \
  -H "Authorization: Token <ADMIN_TOKEN>"
```

The token must belong to a staff/superuser or linked Telegram admin.

### 10.14 clear_data Command Fails On MySQL

Cause:

- `bot/management/commands/clear_data.py` uses SQLite-only statements:
  - `PRAGMA foreign_keys`
  - `DELETE FROM sqlite_sequence`

Fix:

- Do not run `clear_data` in production.
- Write a MySQL-safe reset command only for staging if absolutely needed.

### 10.15 Logs Not Written

Cause:

- `logs/` missing or not writable.

Fix:

```bash
cd /home/<CPANEL_USER>/repositories/personalV1
mkdir -p logs
chmod 755 logs
touch logs/django.log logs/error.log
chmod 664 logs/django.log logs/error.log
```

### 10.16 HSTS Warning From check --deploy

`python manage.py check --deploy` warned that `SECURE_HSTS_SECONDS` is missing. Start with:

```env
SECURE_HSTS_SECONDS=0
```

After SSL is stable, use:

```env
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=False
```

Do not enable preload until you are certain every subdomain supports HTTPS.

## APPENDIX: Quick Reference Commands

Local checks:

```bash
python manage.py check
python manage.py collectstatic --dry-run --noinput
python -m pytest
```

Production setup:

```bash
source /home/<CPANEL_USER>/virtualenv/repositories/personalV1/3.12/bin/activate
cd /home/<CPANEL_USER>/repositories/personalV1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py bot_webhook set
python manage.py bot_webhook status
```

Static test:

```bash
curl -I https://<YOUR_DOMAIN>/static/admin/css/base.css
```

Health test:

```bash
curl https://<YOUR_DOMAIN>/api/health/
```

Webhook status:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

Cron examples:

```bash
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/process-timeouts/" -H "Authorization: Token <ADMIN_TOKEN>"
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/send-surveys/" -H "Authorization: Token <ADMIN_TOKEN>"
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/send-mass-reminders/" -H "Authorization: Token <ADMIN_TOKEN>"
curl -sS -X POST "https://<YOUR_DOMAIN>/api/admin/request-location-updates/" -H "Authorization: Token <ADMIN_TOKEN>"
```

Logs:

```bash
tail -n 100 /home/<CPANEL_USER>/repositories/personalV1/logs/error.log
tail -n 100 /home/<CPANEL_USER>/repositories/personalV1/logs/django.log
```

## APPENDIX: File Structure Reference

Upload target:

```text
/home/<CPANEL_USER>/repositories/personalV1/
  accounts/
  adminpanel/
  approvals/
  bot/
    management/
      commands/
        bot_webhook.py
        clear_data.py
        seed_demo_services.py
  health/
  marketplace/
    __init__.py
    settings.py
    urls.py
    wsgi.py
    asgi.py
    api/
      exceptions.py
  matching/
  miniapp/
  moderation/
  services/
  swipes/
  templates/
    400.html
    403.html
    404.html
    500.html
    adminpanel/
    miniapp/
      app.html
  verification/
  manage.py
  passenger_wsgi.py
  requirements.txt
  logs/
```

Public web root:

```text
/home/<CPANEL_USER>/public_html/
  .htaccess
  static/
    admin/
    rest_framework/
  media/
```

Files to keep out of public web root:

```text
.env
db.sqlite3
venv/
.git/
.pytest_cache/
logs/
*.pyc
__pycache__/
```

## Final Deployment Order

1. Apply the production code changes.
2. Create `requirements.txt`.
3. Create `passenger_wsgi.py`.
4. Create error pages.
5. Create cPanel MySQL database/user.
6. Create cPanel Python app.
7. Add cPanel environment variables.
8. Upload code to `/home/<CPANEL_USER>/repositories/personalV1`.
9. Install requirements.
10. Run `python manage.py check`.
11. Run `python manage.py migrate`.
12. Create superuser.
13. Run `python manage.py collectstatic --noinput`.
14. Confirm app loads over HTTPS.
15. Set Telegram webhook.
16. Test `/start` in Telegram.
17. Add cPanel cron jobs with token auth.
18. Monitor `logs/error.log` and Telegram webhook status.
