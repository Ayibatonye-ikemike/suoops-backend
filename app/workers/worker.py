from __future__ import annotations

from app.workers.celery_app import celery_app


def main() -> None:
    """Convenience entrypoint for launching the Celery worker."""
    celery_app.worker_main(["worker", "--loglevel=info"])


if __name__ == "__main__":
    main()
