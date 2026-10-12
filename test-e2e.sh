#!/usr/bin/env bash
# Tests de bout en bout dans un vrai navigateur (Firefox headless + Selenium). Démarre sa propre API et son propre front.
# Prérequis : Firefox ; `pip install selenium` dans un environnement quelconque (le pilote geckodriver est téléchargé
# automatiquement par Selenium). Variable FIREFOX_BIN pour un autre emplacement de Firefox.
cd "$(dirname "$0")" || exit 1
PY=${E2E_PYTHON:-python3}
"$PY" -c "import selenium" 2>/dev/null || { echo "Selenium manquant : $PY -m pip install selenium (ou définir E2E_PYTHON)"; exit 2; }
exec "$PY" -m unittest discover -s e2e -v "$@"
