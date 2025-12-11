# backend/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()




# import os
# from celery import Celery
# from celery.schedules import crontab

# # 1️⃣ Set Django settings module
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

# # 2️⃣ Create Celery app
# app = Celery("backend")
# app.config_from_object("django.conf:settings", namespace="CELERY")
# app.autodiscover_tasks()

# # 3️⃣ Optional Beat schedule (for testing)
# app.conf.beat_schedule = {
#     "run-lottery-every-10-seconds": {
#         "task": "api.tasks.start_new_round",  # your task name
#         "schedule": 10.0,  # every 10 seconds for testing
#     },
# }

# # 4️⃣ Optional timezone
# app.conf.timezone = "UTC"
