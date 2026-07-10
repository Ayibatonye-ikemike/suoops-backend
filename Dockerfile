FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for weasyprint and other packages
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Drop root: run as a non-privileged user (defense-in-depth vs container escape).
# Give it a home + writable XDG cache so fontconfig/weasyprint can build their
# caches (otherwise: "Fontconfig error: No writable cache directories").
RUN groupadd -r appuser \
    && useradd -r -g appuser -m -d /home/appuser appuser \
    && mkdir -p /home/appuser/.cache/fontconfig \
    && chown -R appuser:appuser /app /home/appuser
ENV HOME=/home/appuser \
    XDG_CACHE_HOME=/home/appuser/.cache
USER appuser

EXPOSE 8000

CMD ["gunicorn", "app.api.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "--bind", "0.0.0.0:8000"]
