release: bash release.sh
## Production server: Gunicorn with Uvicorn workers for multi-process concurrency
## Reduced workers from 4 to 2 to fit in 512M memory quota (was hitting R14 errors at 545M)
web: gunicorn app.api.main:app -k uvicorn.workers.UvicornWorker -w 2 --threads 2 --max-requests 2000 --max-requests-jitter 200 --timeout 60 --bind 0.0.0.0:$PORT
# Concurrency capped to 1 to mitigate R14 memory spikes; tune via CELERYD_CONCURRENCY env for scaling.
worker: celery -A app.workers.celery_app worker --loglevel=info --concurrency=${CELERYD_CONCURRENCY:-1}