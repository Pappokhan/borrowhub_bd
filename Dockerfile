FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN sed -i 's/\r$//' deploy/entrypoint.sh && chmod +x deploy/entrypoint.sh \
 && adduser --disabled-password --gecos "" app \
 && mkdir -p /data/media /data/private_media staticfiles \
 && DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-time-only-key-build-time-only-key-build-time python manage.py collectstatic --noinput \
 && chown -R app:app /app /data
USER app

ENV DJANGO_DEBUG=0 DJANGO_MEDIA_ROOT=/data/media DJANGO_PRIVATE_MEDIA_ROOT=/data/private_media TRUST_PROXY_HEADERS=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=4).status == 200 else 1)"
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]
