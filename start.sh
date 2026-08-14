#!/usr/bin/env bash
# EchoHub v2 — démarrage.
#
#   ./start.sh            mode natif : uvicorn + serveur Vite, rechargement à chaud
#   ./start.sh --docker   mode conteneur : image GPU complète (docker compose)
#
# Le mode natif ne compile pas llama-cpp-python pour CUDA : c'est le rôle de l'image Docker.
# Il sert au développement de l'interface et de la logique, pas à mesurer le GPU.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$RACINE/logs"
MODE="natif"

journal() { echo "[start] $*"; }
echec()   { echo "[start] ERREUR : $*" >&2; exit 1; }

charger_env() {
    [ -f "$RACINE/.env" ] || return 0
    set -a
    # shellcheck disable=SC1091
    . "$RACINE/.env"
    set +a
    journal ".env chargé"
}

# Les journaux sont remis à zéro à chaque démarrage : un fichier de log qui s'accumule sur
# plusieurs sessions ne permet plus de dire quelle exécution a produit quelle erreur.
reinitialiser_logs() {
    mkdir -p "$LOGS"
    : > "$LOGS/backend.log"
    : > "$LOGS/frontend.log"
    journal "journaux remis à zéro dans $LOGS"
}

# Un PID encore vivant signifie une instance déjà lancée : démarrer par-dessus donnerait deux
# processus sur le même port et un fichier de PID mensonger.
verifier_libre() {
    local fichier="$LOGS/$1.pid"
    [ -f "$fichier" ] || return 0
    local pid
    pid="$(cat "$fichier")"
    if kill -0 "$pid" 2>/dev/null; then
        echec "$1 tourne déjà (PID $pid) — lancer ./stop.sh d'abord"
    fi
    rm -f "$fichier"
}

# Le venv est en layout POSIX ou Windows selon la machine : on ne devine pas, on regarde.
python_venv() {
    if [ -x "$RACINE/backend/.venv/bin/python" ]; then
        echo "$RACINE/backend/.venv/bin/python"
    elif [ -x "$RACINE/backend/.venv/Scripts/python.exe" ]; then
        echo "$RACINE/backend/.venv/Scripts/python.exe"
    fi
}

preparer_backend() {
    if [ -z "$(python_venv)" ]; then
        journal "création du venv backend"
        python3 -m venv "$RACINE/backend/.venv" || echec "création du venv impossible"
    fi
    local py
    py="$(python_venv)"
    [ -n "$py" ] || echec "interpréteur du venv introuvable après création"
    "$py" -m pip install --quiet --upgrade pip \
        || echec "mise à jour de pip impossible"
    "$py" -m pip install --quiet -r "$RACINE/backend/requirements.txt" \
        || echec "installation des dépendances backend impossible"
    journal "dépendances backend à jour"
}

preparer_frontend() {
    command -v bun >/dev/null 2>&1 || echec "bun introuvable — https://bun.sh"
    [ -d "$RACINE/frontend/node_modules" ] && return 0
    journal "installation des dépendances frontend"
    (cd "$RACINE/frontend" && bun install) || echec "bun install a échoué"
}

# Attente bornée : 60 tentatives d'une seconde. Sans borne, un backend qui ne démarre jamais
# ferait tourner ce script indéfiniment sans rien dire.
attendre_api() {
    local port="$1" i
    for i in $(seq 1 60); do
        if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
            journal "API disponible sur 127.0.0.1:$port (après ${i}s)"
            return 0
        fi
        sleep 1
    done
    journal "AVERTISSEMENT : API muette après 60s — voir $LOGS/backend.log"
}

demarrer_natif() {
    local port_api="${ECHOHUB_PORT_API:-37821}" port_front="${ECHOHUB_PORT_FRONT_DEV:-37822}"
    verifier_libre backend
    verifier_libre frontend
    preparer_backend
    preparer_frontend

    local py
    py="$(python_venv)"
    journal "backend sur 127.0.0.1:$port_api"
    (cd "$RACINE" && PYTHONPATH="$RACINE" "$py" -m uvicorn backend.main:app \
        --host 127.0.0.1 --port "$port_api" --reload >>"$LOGS/backend.log" 2>&1 &
        echo $! > "$LOGS/backend.pid")

    journal "frontend sur 127.0.0.1:$port_front"
    (cd "$RACINE/frontend" && bun run dev --port "$port_front" >>"$LOGS/frontend.log" 2>&1 &
        echo $! > "$LOGS/frontend.pid")

    attendre_api "$port_api"
    journal "interface : http://127.0.0.1:$port_front"
}

demarrer_docker() {
    command -v docker >/dev/null 2>&1 || echec "docker introuvable"
    mkdir -p "$LOGS"
    journal "construction et démarrage du conteneur (première fois : compilation CUDA, longue)"
    (cd "$RACINE" && docker compose up -d --build) || echec "docker compose up a échoué"
    journal "interface : http://127.0.0.1:${ECHOHUB_PORT_WEB:-37820}"
    journal "journaux : docker compose logs -f echohub"
}

case "${1:-}" in
    --docker) MODE="docker" ;;
    --help|-h) sed -n '2,8p' "$0"; exit 0 ;;
    "") ;;
    *) echec "option inconnue : $1" ;;
esac

charger_env
if [ "$MODE" = "docker" ]; then
    demarrer_docker
else
    reinitialiser_logs
    demarrer_natif
fi
