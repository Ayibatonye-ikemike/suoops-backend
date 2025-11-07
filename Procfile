release: bash release.sh
web: uvicorn app.api.main:app --host 0.0.0.0 --port $PORT
# Concurrency capped to 1 to mitigate R14 memory spikes; tune via CELERYD_CONCURRENCY env for scaling.
worker: celery -A app.workers.celery_app worker --loglevel=info --concurrency=${CELERYD_CONCURRENCY:-1}