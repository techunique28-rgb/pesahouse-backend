import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pesahouse.settings.dev")

app = Celery("pesahouse")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
