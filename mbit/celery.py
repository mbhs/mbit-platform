from __future__ import absolute_import
from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mbit.settings')

app = Celery('mbit')
app.conf.broker_url = "redis://" + os.environ.get("REDIS_HOST", "localhost") + "/0"
app.conf.worker_prefetch_multiplier = 1
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
