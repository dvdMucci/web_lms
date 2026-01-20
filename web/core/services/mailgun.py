import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MailgunClient:
    def __init__(self):
        self.base_url = settings.MAILGUN_BASE_URL
        self.domain = settings.MAILGUN_DOMAIN
        self.api_key = settings.MAILGUN_API_KEY
        self.from_email = settings.MAILGUN_FROM_EMAIL
        self.timeout = settings.MAILGUN_TIMEOUT
        self.enabled = settings.MAILGUN_ENABLED

    def send_message(self, to_email, subject, text, html=None, from_email=None, tags=None):
        if not self.enabled:
            logger.warning("Mailgun no está configurado; email omitido.")
            return False
        if not to_email:
            logger.warning("Email de destino vacío; email omitido.")
            return False

        data = {
            "from": from_email or self.from_email,
            "to": to_email,
            "subject": subject,
            "text": text,
        }
        if html:
            data["html"] = html
        if tags:
            data["o:tag"] = tags

        try:
            response = requests.post(
                f"{self.base_url}/v3/{self.domain}/messages",
                auth=("api", self.api_key),
                data=data,
                timeout=self.timeout,
            )
            if not response.ok:
                logger.warning(
                    "Fallo Mailgun. status=%s body=%s",
                    response.status_code,
                    response.text,
                )
            return response.ok
        except requests.RequestException:
            logger.exception("Error al enviar email con Mailgun.")
            return False
