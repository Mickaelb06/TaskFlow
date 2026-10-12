#!/usr/bin/env bash
# Lance TaskFlow en local (API Django + front statique) et ouvre le navigateur.
#   ./start.sh         démarrer      ./start.sh stop     arrêter
cd "$(dirname "$0")" || exit 1
PY=backend/.venv/bin/python
mkdir -p .logs

if [ "$1" = "stop" ]; then
  pkill -f "manage.py runserver" 2>/dev/null; pkill -f "serve.py 5173" 2>/dev/null; pkill -f "http.server 5173" 2>/dev/null
  echo "Serveurs arrêtés."; exit 0
fi
[ -x "$PY" ] || { echo "Environnement manquant : voir le README (python -m venv backend/.venv && pip install -r backend/requirements.txt)"; exit 1; }

pkill -f "manage.py runserver" 2>/dev/null; pkill -f "serve.py 5173" 2>/dev/null; pkill -f "http.server 5173" 2>/dev/null; sleep 1
export USE_SQLITE=${USE_SQLITE:-1}   # base locale SQLite ; mettre USE_SQLITE=0 pour PostgreSQL
# migrations d'abord, au premier plan ; puis chaque serveur en arrière-plan, entièrement détaché du terminal
( cd backend && "../$PY" manage.py migrate -v0 )
( cd backend; nohup "../$PY" manage.py runserver 8000 --noreload > ../.logs/api.log 2>&1 < /dev/null & )
( cd frontend; nohup python3 serve.py 5173 > ../.logs/front.log 2>&1 < /dev/null & )

printf "Démarrage de l'API"
for _ in $(seq 1 60); do
  curl -s -m 1 localhost:8000/health/ >/dev/null 2>&1 && break
  printf "."; sleep 1
done
echo
if curl -s -m 2 localhost:8000/health/ >/dev/null 2>&1; then
  echo "✔ API    http://localhost:8000"
  echo "✔ Appli  http://localhost:5173   (compte démo : demo / demo-taskflow-2026)"
  open http://localhost:5173 >/dev/null 2>&1 || true
else
  echo "✘ L'API n'a pas démarré — voir .logs/api.log"; tail -n 15 .logs/api.log; exit 1
fi
