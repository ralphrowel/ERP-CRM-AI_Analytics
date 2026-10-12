"""Production Event Worker & Scheduled Business Automation Daemon (Roadmap §V1.9)

Runs in a separate container/process alongside the API server:
- Continuous polling of outbox_events with exponential backoff and dead-letter handling.
- Periodic execution of scheduled business automation checks (every hour / daily).
- Graceful shutdown handling on SIGTERM / SIGINT.
"""

import logging
import signal
import time

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.events.mailer import EmailDispatcher
from app.modules.events.scheduler import ScheduledChecksEngine
from app.modules.events.worker import OutboxWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [worker_daemon] %(message)s",
)
logger = logging.getLogger("worker_daemon")

_RUNNING = True


def _handle_exit(signum, frame):
    global _RUNNING
    logger.info("Received termination signal (%s). Initiating graceful shutdown...", signum)
    _RUNNING = False


def run_daemon(poll_interval: float = 1.0, scheduler_interval_seconds: int = 3600) -> None:
    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)

    mailer = EmailDispatcher(
        smtp_host=settings.SMTP_HOST,
        smtp_port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        use_tls=settings.SMTP_USE_TLS,
        from_email=settings.DEFAULT_FROM_EMAIL,
    )
    worker = OutboxWorker(db_factory=SessionLocal, mailer=mailer)

    last_scheduled_check = 0.0
    logger.info(
        "Outbox Worker & Scheduler Daemon started (poll=%.1fs, scheduler=%ds)",
        poll_interval,
        scheduler_interval_seconds,
    )

    while _RUNNING:
        now = time.time()

        # 1. Run scheduled business automation checks periodically
        if now - last_scheduled_check >= scheduler_interval_seconds:
            try:
                with SessionLocal() as db:
                    logger.info("Executing scheduled business checks engine...")
                    results = ScheduledChecksEngine.run_all_scheduled_checks(db)
                    logger.info("Scheduled checks completed: %s", results)
                last_scheduled_check = now
            except Exception as exc:
                logger.error("Error during scheduled checks execution: %s", exc, exc_info=True)

        # 2. Process pending outbox events batch
        try:
            processed = worker.process_batch(batch_size=50)
            if processed == 0:
                time.sleep(poll_interval)
        except Exception as exc:
            logger.error("Error during outbox batch processing: %s", exc, exc_info=True)
            time.sleep(poll_interval)

    logger.info("Worker daemon stopped gracefully.")


if __name__ == "__main__":
    run_daemon()
