release: python -m alembic -c alembic.ini upgrade head
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
worker: celery -A services.tasks.celery_app worker --loglevel=info
scheduler: celery -A services.tasks.celery_app beat --loglevel=info --schedule /tmp/celerybeat-schedule
