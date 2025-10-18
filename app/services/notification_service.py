from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NotificationService:
    def send_invoice_created(self, to: str, invoice_id: str):
        logger.info("Notify %s invoice %s created", to, invoice_id)
