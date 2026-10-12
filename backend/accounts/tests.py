from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


class AuthTests(APITestCase):
    def test_register_then_login_then_me(self):
        res = self.client.post(
            "/api/auth/register/", {"username": "alice", "email": "a@x.fr", "password": "Mot-de-passe-9"}
        )
        self.assertEqual(res.status_code, 201)
        self.assertNotIn("password", res.data)

        tok = self.client.post("/api/auth/token/", {"username": "alice", "password": "Mot-de-passe-9"})
        self.assertEqual(tok.status_code, 200)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tok.data['access']}")
        me = self.client.get("/api/me/")
        self.assertEqual(me.data["username"], "alice")

    def test_weak_password_rejected(self):
        res = self.client.post("/api/auth/register/", {"username": "bob", "email": "b@x.fr", "password": "123"})
        self.assertEqual(res.status_code, 400)

    def test_duplicate_email_rejected(self):
        User.objects.create_user("alice", "a@x.fr", "Mot-de-passe-9")
        res = self.client.post(
            "/api/auth/register/", {"username": "alice2", "email": "A@x.fr", "password": "Mot-de-passe-9"}
        )
        self.assertEqual(res.status_code, 400)
