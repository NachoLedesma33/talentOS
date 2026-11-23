FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Misma instalación que la API: pypdf, python-docx y celery vienen de pyproject.toml.
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/app ./app
RUN pip install --no-cache-dir -e .

CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "--loglevel=info"]
