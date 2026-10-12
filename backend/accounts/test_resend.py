import json
from unittest import mock

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from .resend_backend import ResendEmailBackend


class ResendBackendTests(SimpleTestCase):
    @mock.patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @mock.patch("accounts.resend_backend.urllib.request.urlopen")
    def test_envoie_le_message_a_l_api(self, urlopen):
        n = ResendEmailBackend().send_messages([EmailMessage("Sujet", "Corps", "TaskFlow <a@x.fr>", ["b@x.fr"])])
        self.assertEqual(n, 1)
        req = urlopen.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bearer re_test")
        self.assertEqual(json.loads(req.data)["to"], ["b@x.fr"])

    @mock.patch("accounts.resend_backend.urllib.request.urlopen", side_effect=OSError("réseau"))
    def test_erreur_reseau_levee_ou_ignoree(self, _):
        msg = EmailMessage("S", "C", "a@x.fr", ["b@x.fr"])
        with self.assertRaises(OSError), self.assertLogs("accounts.resend_backend", "ERROR"):
            ResendEmailBackend().send_messages([msg])
        with self.assertLogs("accounts.resend_backend", "ERROR"):
            self.assertEqual(ResendEmailBackend(fail_silently=True).send_messages([msg]), 0)
