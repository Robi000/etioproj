#!/usr/bin/env bash

cd "/c/Users/rabeb/OneDrive/Desktop/personalV1"

source venv/Scripts/activate

echo ""
echo "Setting Telegram Webhook..."
echo ""

python manage.py bot_webhook set

echo ""
echo "Webhook Status"
echo ""

python manage.py bot_webhook status
