#!/bin/bash
# EchoHub — point d'entrée du conteneur.
# Lance le backend FastAPI (uvicorn, écoute 0.0.0.0:37821 — le conteneur n'a pas de coquille
# Tauri pour lui fournir un port dynamique via lib.rs, donc on fixe le port standard du projet)
# et nginx (sert le frontend statique + proxifie /api). Les deux tournent en avant-plan du
# conteneur ; un SIGTERM reçu par le conteneur est relayé aux deux pour un arrêt propre.
set -euo pipefail

mkdir -p "${MODELS_DIR:-/data/models}" "${XDG_DATA_HOME:-/data/user}"

echo "[entrypoint] démarrage backend uvicorn sur 0.0.0.0:37821"
/app/backend/.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 37821 &
UVICORN_PID=$!

echo "[entrypoint] démarrage nginx sur :80"
nginx -g "daemon off;" &
NGINX_PID=$!

terminate() {
    echo "[entrypoint] signal reçu, arrêt propre..."
    kill -TERM "$UVICORN_PID" "$NGINX_PID" 2>/dev/null || true
    wait "$UVICORN_PID" "$NGINX_PID" 2>/dev/null || true
}
trap terminate TERM INT

# Si l'un des deux process meurt, on arrête le conteneur plutôt que de tourner à moitié mort.
wait -n "$UVICORN_PID" "$NGINX_PID"
EXIT_CODE=$?
terminate
exit "$EXIT_CODE"
