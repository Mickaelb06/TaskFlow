import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "corsheaders",
    "rest_framework",
    "accounts",
    "projects",
    "tasks",
    "agenda",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "taskflow.urls"
WSGI_APPLICATION = "taskflow.wsgi.application"

if os.environ.get("USE_SQLITE") == "1":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3")}}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "taskflow"),
            "USER": os.environ.get("POSTGRES_USER", "taskflow"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "taskflow"),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "EXCEPTION_HANDLER": "taskflow.exceptions.handler",
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # Limites de débit par portée (`throttle_scope` sur la vue). Derrière un proxy, régler NUM_PROXIES.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "login": os.environ.get("LOGIN_RATE", "10/min"),        # essais de connexion par adresse IP (force brute)
        "register": os.environ.get("REGISTER_RATE", "10/hour"),  # créations de compte par adresse IP
        "chat": os.environ.get("CHAT_RATE", "60/min"),          # messages envoyés par utilisateur
        "account": os.environ.get("ACCOUNT_RATE", "10/hour"),   # export / suppression de son compte
    },
}

SIMPLE_JWT = {"UPDATE_LAST_LOGIN": True}  # alimente « dernière connexion » dans l'administration

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_TZ = True
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))  # pièces jointes de la messagerie (jamais servies directement)
MEDIA_URL = None
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS : nécessaire pour le front Flutter web ; en production, lister les origines autorisées
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o]

if "test" in sys.argv[:2]:  # tests : hachage rapide (PBKDF2 ralentit chaque création de compte) — jamais en production
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
