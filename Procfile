release: python manage.py migrate --noinput
web: gunicorn config.wsgi:application -c gunicorn.conf.py
