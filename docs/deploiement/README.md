# Déploiement

## Architecture
```mermaid
flowchart LR
    B[Navigateur] -->|:8080| W[web — nginx<br>fichiers statiques + proxy /api]
    W -->|/api| A[api — Django + gunicorn :8000]
    A --> D[(db — PostgreSQL 16)]
```

## Lancer
```bash
cp .env.example .env     # puis ajuster les secrets
docker compose up --build
```
L'image `api` applique les migrations au démarrage. Volumes : `pgdata` (base) et `media` (pièces jointes de la messagerie) — **tous deux à sauvegarder**.

## Développement local
`./start.sh` lance l'API (port 8000) et le front (port 5173, `frontend/serve.py` : aucun cache navigateur) puis ouvre le navigateur ; `./start.sh stop` arrête tout. Journaux dans `.logs/`.

## Variables d'environnement
| Variable | Rôle | Production |
|---|---|---|
| `DJANGO_SECRET_KEY` | clé de signature | valeur aléatoire longue (≥ 32 caractères) |
| `DJANGO_DEBUG` | mode debug | `0` |
| `DJANGO_ALLOWED_HOSTS` | hôtes autorisés | votre domaine |
| `CORS_ALLOWED_ORIGINS` | origines autorisées si front sur un autre domaine | à définir |
| `POSTGRES_*` | connexion base | mots de passe forts |
| `SITE_URL` | adresse publique du front (liens des e-mails) | `https://taskflow.exemple.fr` |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | envoi des e-mails (mentions, invitations, résumé) ; par défaut ils s'affichent dans la console | SMTP du fournisseur, identifiants dans un gestionnaire de secrets |
| `MEDIA_ROOT` | dossier des pièces jointes (volume `media` dans Docker) | volume persistant **sauvegardé** |
| `LOGIN_RATE`, `REGISTER_RATE`, `CHAT_RATE`, `ACCOUNT_RATE` | limites de débit (`10/min`, `10/hour`, `60/min`, `10/hour`) | à ajuster selon le trafic |
| `NUM_PROXIES` | nombre de proxys devant l'API (pour lire la vraie adresse IP des clients) | `1` derrière nginx |

## Image de l'API
`backend/Dockerfile` : étape 1 compile le module Rust (rustup + maturin, roue abi3, `cargo test` inclus), étape 2 installe la roue dans une image Python sans compilateur. Si le module est absent, l'application tourne avec la version Python (visible dans `/health/` → `planning_engine`).

## Tâches planifiées
Le résumé du matin n'est envoyé que si on le planifie (aucun processus en arrière-plan n'est démarré par l'application) : `0 7 * * 1-5  cd /app && python manage.py send_digest` (cron de l'hôte, ou `docker compose exec api python manage.py send_digest`). `--dry-run` affiche les résumés sans rien envoyer.

## Application installable (PWA)
Le front fournit un manifeste, des icônes et un service worker (`frontend/sw.js`, « réseau d'abord ») : le navigateur propose d'installer l'application. Cela exige **HTTPS** (sauf localhost) ; le service worker n'est enregistré qu'hors localhost. Les requêtes `/api/` ne sont jamais mises en cache.

## Intégration continue
`.github/workflows/ci.yml` : sur chaque push, démarre PostgreSQL, installe les dépendances, vérifie qu'aucune migration n'est oubliée, lance les tests — en **matrice** : une fois avec le moteur Rust (tests Rust + compilation), une fois avec le moteur Python. Un second job **e2e** lance les 33 scénarios de bout en bout dans Firefox headless (`./test-e2e.sh`).

## À faire
Passer `gunicorn` derrière HTTPS (reverse proxy), sauvegarde planifiée de la base (`pg_dump`), build et publication des images dans la CI.
