release: bash release.sh
## Production server: Gunicorn with Uvicorn workers
## Reduced to 1 worker to fit in 512M memory quota on Render starter plan
web: gunicorn app.api.main:app -k uvicorn.workers.UvicornWorker -w 1 --threads 2 --max-requests 2000 --max-requests-jitter 200 --timeout 60 --bind 0.0.0.0:$PORT
# Concurrency 1 to stay under 512MB memory limit
worker: celery -A app.workers.celery_app worker --beat --loglevel=info --concurrency=${CELERYD_CONCURRENCY:-1}