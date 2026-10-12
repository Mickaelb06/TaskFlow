from urllib.parse import unquote, urlsplit


def parse_database_url(url):
    """Convertit une adresse `postgresql://utilisateur:mdp@hôte:port/base` (fournie par Railway, Heroku…) en réglage DATABASES."""
    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL : seul PostgreSQL est pris en charge")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parts.path.lstrip("/")),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "localhost",
        "PORT": str(parts.port or 5432),
    }
