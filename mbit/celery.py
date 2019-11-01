from __future__ import absolute_import
from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mbit.settings')

app = Celery('mbit')
app.conf.broker_url = 'redis://'
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
