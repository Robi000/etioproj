# Simple cPanel Hosting Guide

Short, practical steps for hosting this Django Telegram Mini App.

Project folder: `personalV1`  
Django settings: `marketplace/settings.py`  
Webhook URL path: `/api/bot/webhook/`  
Mini App page: `/`

Replace these:

```text
<CPANEL_USER>      your cPanel username
<YOUR_DOMAIN>      your domain, example: example.com
<BOT_TOKEN>        Telegram bot token
<BOT_USERNAME>     Telegram bot username without @
<WEBHOOK_SECRET>   long random secret text
<DB_PASSWORD>      cPanel database password
```

## 1. Make These Local File Changes

### Create `requirements.txt`

Run locally:

```powershell
venv\Scripts\python.exe -m pip freeze > requirements.txt
```

Open `requirements.txt` and add:

```text
mysqlclient==2.2.4
```

### Update Database Settings

In `marketplace/settings.py`, replace the current `DATABASES` block with:

```python
DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.sqlite3"),
        "NAME": config("DB_NAME", default=BASE_DIR / "db.sqlite3"),
        "USER": config("DB_USER", default=""),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default=""),
        "PORT": config("DB_PORT", default=""),
    }
}
```

Below `CORS_ALLOWED_ORIGINS`, add:

```python
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
```

### Create `passenger_wsgi.py`

Create `passenger_wsgi.py` beside `manage.py`:

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

## 2. Create MySQL Database in cPanel

In cPanel, open **MySQL Databases**.

Create:

```text
Database: <CPANEL_USER>_marketplace
User:     <CPANEL_USER>_marketuser
Password: <DB_PASSWORD>
```

Add the user to the database and give **ALL PRIVILEGES**.

## 3. Create Python App in cPanel

Open **Setup Python App**.

Use:

```text
Python version: 3.11 or 3.12
Application root: personalV1
Application URL: <YOUR_DOMAIN>
Startup file: passenger_wsgi.py
Entry point: application
```

After creating it, cPanel will show an activate command like:

```bash
source /home/<CPANEL_USER>/virtualenv/personalV1/3.11/bin/activate
```

Keep that command.

## 4. Add Environment Variables

In the cPanel Python App screen, add:

```text
DEBUG=False
SECRET_KEY=<generate-a-new-django-secret-key>
ALLOWED_HOSTS=<YOUR_DOMAIN>,www.<YOUR_DOMAIN>

DB_ENGINE=django.db.backends.mysql
DB_NAME=<CPANEL_USER>_marketplace
DB_USER=<CPANEL_USER>_marketuser
DB_PASSWORD=<DB_PASSWORD>
DB_HOST=localhost
DB_PORT=3306

TELEGRAM_BOT_TOKEN=<BOT_TOKEN>
TELEGRAM_BOT_USERNAME=<BOT_USERNAME>
TELEGRAM_MINI_APP_URL=https://<YOUR_DOMAIN>/
TELEGRAM_WEBHOOK_URL=https://<YOUR_DOMAIN>/api/bot/webhook/
BOT_WEBHOOK_SECRET=<WEBHOOK_SECRET>
BOT_WEBHOOK_ASYNC=True

CORS_ALLOWED_ORIGINS=https://<YOUR_DOMAIN>
CSRF_TRUSTED_ORIGINS=https://<YOUR_DOMAIN>
LOG_LEVEL=INFO
```

Generate `SECRET_KEY` locally:

```powershell
venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 5. Upload Files

Upload this project to:

```text
/home/<CPANEL_USER>/personalV1
```

Upload these:

```text
manage.py
passenger_wsgi.py
requirements.txt
marketplace/
accounts/
adminpanel/
approvals/
bot/
health/
matching/
miniapp/
moderation/
services/
swipes/
templates/
verification/
media/
static/
logs/
```

Do not upload:

```text
venv/
.git/
.pytest_cache/
db.sqlite3
old log files
```

## 6. Install and Start Django

Open cPanel Terminal:

```bash
source /home/<CPANEL_USER>/virtualenv/personalV1/3.11/bin/activate
cd /home/<CPANEL_USER>/personalV1
pip install --upgrade pip
pip install -r requirements.txt
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

Then go back to **Setup Python App** and click **Restart**.

## 7. Static and Media Files

Run this in cPanel Terminal:

```bash
ln -s /home/<CPANEL_USER>/personalV1/staticfiles /home/<CPANEL_USER>/public_html/static
ln -s /home/<CPANEL_USER>/personalV1/media /home/<CPANEL_USER>/public_html/media
```

If symlinks are blocked, copy instead:

```bash
cp -r /home/<CPANEL_USER>/personalV1/staticfiles /home/<CPANEL_USER>/public_html/static
cp -r /home/<CPANEL_USER>/personalV1/media /home/<CPANEL_USER>/public_html/media
```

## 8. Set Telegram Webhook

Run:

```bash
cd /home/<CPANEL_USER>/personalV1
source /home/<CPANEL_USER>/virtualenv/personalV1/3.11/bin/activate
python manage.py bot_webhook set
python manage.py bot_webhook status
```

The status should show:

```text
https://<YOUR_DOMAIN>/api/bot/webhook/
```

## 9. Test

Open:

```text
https://<YOUR_DOMAIN>/
https://<YOUR_DOMAIN>/dashboard/admin/
https://<YOUR_DOMAIN>/api/health/
```

Then in Telegram:

```text
Send /start
Open the Mini App
Check that the marketplace loads
```

## 10. If Something Breaks

### 500 error

Check:

```bash
tail -100 /home/<CPANEL_USER>/personalV1/logs/error.log
tail -100 /home/<CPANEL_USER>/personalV1/logs/django.log
```

Most likely causes:

```text
Wrong DB password
Missing environment variable
Package failed to install
SSL redirect before SSL is ready
```

### Static files missing

Run:

```bash
python manage.py collectstatic --noinput
```

Then confirm:

```text
/home/<CPANEL_USER>/public_html/static
```

### Bot not responding

Run:

```bash
python manage.py bot_webhook set
python manage.py bot_webhook status
```

Also confirm these are correct:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_WEBHOOK_URL
BOT_WEBHOOK_SECRET
TELEGRAM_MINI_APP_URL
```

### Mini App opens but only shows background

Check these first:

```text
CORS_ALLOWED_ORIGINS=https://<YOUR_DOMAIN>
CSRF_TRUSTED_ORIGINS=https://<YOUR_DOMAIN>
TELEGRAM_MINI_APP_URL=https://<YOUR_DOMAIN>/
```

Then inspect failed API calls:

```text
/api/me/
/api/discovery/grid/
/api/discovery/swipe/
```

## Final Checklist

- [ ] `requirements.txt` created.
- [ ] `passenger_wsgi.py` created.
- [ ] MySQL database created.
- [ ] cPanel Python App created.
- [ ] Environment variables added.
- [ ] Project uploaded.
- [ ] `pip install -r requirements.txt` worked.
- [ ] `python manage.py migrate` worked.
- [ ] `python manage.py collectstatic --noinput` worked.
- [ ] Python App restarted.
- [ ] Static/media paths connected.
- [ ] `python manage.py bot_webhook set` worked.
- [ ] Website opens.
- [ ] Telegram bot responds.
- [ ] Mini App opens and loads marketplace data.
