import json
import logging
import os
import urllib.request

from django.core.mail.backends.base import BaseEmailBackend

log = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """Envoi par l'API HTTP de Resend (aucune dépendance) : les hébergeurs comme Railway bloquent souvent le SMTP sortant.

    Réglage : EMAIL_BACKEND=accounts.resend_backend.ResendEmailBackend, RESEND_API_KEY, DEFAULT_FROM_EMAIL (domaine vérifié chez Resend).
    """

    url = "https://api.resend.com/emails"

    def send_messages(self, email_messages):
        key = os.environ.get("RESEND_API_KEY", "")
        sent = 0
        for m in email_messages:
            body = {"from": m.from_email, "to": list(m.to), "subject": m.subject, "text": m.body}
            req = urllib.request.Request(
                self.url, data=json.dumps(body).encode(), method="POST",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "taskflow/1.0"},
            )
            try:
                with urllib.request.urlopen(req, timeout=10):
                    sent += 1
            except Exception:
                log.exception("Resend : envoi impossible à %s", m.to)
                if not self.fail_silently:
                    raise
        return sent
