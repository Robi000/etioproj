# Commands

Activate:

source venv/Scripts/activate

Run migrations:

python manage.py migrate

Create admin:

python manage.py createsuperuser

Run server:

python manage.py runserver

Test health:

curl http://localhost:8000/api/health/

Run tests:

pytest
