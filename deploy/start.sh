#!/bin/bash
# Démarre les migrations, gunicorn (interne) puis nginx ; si l'un des deux s'arrête, le conteneur s'arrête (Railway le relance).
set -e
python manage.py migrate
# premier administrateur : compte déjà inscrit sur le site, nommé par ADMIN_USERNAME (sans effet s'il n'existe pas encore)
if [ -n "$ADMIN_USERNAME" ]; then python manage.py promote_admin "$ADMIN_USERNAME" || true; fi
envsubst '${PORT}' < /etc/nginx/templates/site.conf.template > /etc/nginx/conf.d/site.conf
gunicorn taskflow.wsgi:application -b 127.0.0.1:8000 --workers 1 --threads 8 &
nginx -g 'daemon off;' &
wait -n
exit 1
