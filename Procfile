release: python -m alembic -c alembic.ini upgrade head
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
