#!/usr/bin/env bash

cd "/c/Users/rabeb/OneDrive/Desktop/personalV1"

source venv/Scripts/activate

echo ""
echo "Starting Django Server..."
echo ""

python manage.py runserver
