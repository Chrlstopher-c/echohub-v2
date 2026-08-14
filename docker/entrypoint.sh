#!/usr/bin/env bash
# EchoHub v2 — point d'entrée du conteneur.
# Lance uvicorn (API) et nginx (frontend + proxy) en avant-plan du conteneur, propage SIGTERM
# aux deux, et arrête le conteneur dès que l'un des deux meurt — un conteneur à moitié vivant
# est pire qu'un conteneur mort : il répond « healthy » en ne servant plus rien.
set -euo pipefail

RACINE_STATIQUE="/app/frontend/dist"
MODULE_APP="${ECHOHUB_APP_MODULE:-backend.main:app}"
PORT_API="${ECHOHUB_PORT_API:-37821}"

journal() { echo "[entrypoint] $*"; }

# Mesuré sous WSL2 : la mémoire unifiée n'y supporte pas l'oversubscription, les poids restent
# côté hôte — 20 Go de RAM occupés, VRAM figée à 2 Go, modèle inutilisable. ggml n'active la
# variable que sur sa présence, une valeur vide suffit donc à nuire : on la retire entièrement.
neutraliser_memoire_unifiee() {
    grep -qi microsoft /proc/version 2>/dev/null || return 0
    journal "plateforme WSL2 détectée"
    if [ -n "${GGML_CUDA_ENABLE_UNIFIED_MEMORY+defini}" ]; then
        journal "AVERTISSEMENT : GGML_CUDA_ENABLE_UNIFIED_MEMORY est nuisible sous WSL2, retirée"
        unset GGML_CUDA_ENABLE_UNIFIED_MEMORY
    fi
}

# Empreinte = date de modification la plus récente du dossier statique. Elle change à chaque
# déploiement du frontend, et jamais autrement.
empreinte_statique() {
    find "$RACINE_STATIQUE" -type f -printf '%T@\n' 2>/dev/null \
        | sort -rn | head -1 | cut -d. -f1
}

# Sans empreinte sur les balises <script>/<link>, un déploiement front reste invisible derrière
# le cache du navigateur, rechargement compris — des heures perdues à redéboguer du code déjà
# corrigé. On retire l'empreinte précédente avant d'en poser une nouvelle, sinon un simple
# redémarrage les empilerait sur la même balise.
marquer_assets() {
    local index="$RACINE_STATIQUE/index.html" empreinte
    if [ ! -f "$index" ]; then
        journal "AVERTISSEMENT : $index absent, aucun asset marqué"
        return 0
    fi
    empreinte="$(empreinte_statique)"
    [ -n "$empreinte" ] || empreinte="0"
    sed -i -E "s#(src|href)=\"(/[^\"?]+\.(js|css))(\?v=[^\"]*)?\"#\1=\"\2?v=${empreinte}\"#g" "$index"
    journal "assets statiques marqués ?v=${empreinte}"
}

# Version du binaire compilé, tracée à chaque démarrage : c'est le seul repère écrit avant tout
# chargement de modèle. La ligne « CUDA : ARCHS = 860,1200 | FORCE_CUBLAS = 1 » qui confirme la
# compilation Blackwell n'apparaît, elle, qu'au premier chargement, dans les journaux de ggml.
tracer_moteur() {
    local version
    version="$(python -c 'import llama_cpp; print(llama_cpp.__version__)' 2>/dev/null || true)"
    journal "llama-cpp-python : ${version:-introuvable}"
}

terminer() {
    journal "signal reçu, arrêt propre"
    kill -TERM "$PID_UVICORN" "$PID_NGINX" 2>/dev/null || true
    wait "$PID_UVICORN" "$PID_NGINX" 2>/dev/null || true
}

mkdir -p "${MODELS_DIR:-/data/models}" "${XDG_DATA_HOME:-/data/user}"
neutraliser_memoire_unifiee
marquer_assets
tracer_moteur

journal "démarrage uvicorn ${MODULE_APP} sur 0.0.0.0:${PORT_API}"
python -m uvicorn "$MODULE_APP" --host 0.0.0.0 --port "$PORT_API" &
PID_UVICORN=$!

journal "démarrage nginx sur :80"
nginx -g "daemon off;" &
PID_NGINX=$!

trap terminer TERM INT

CODE_SORTIE=0
wait -n "$PID_UVICORN" "$PID_NGINX" || CODE_SORTIE=$?
journal "un processus s'est arrêté (code ${CODE_SORTIE}), arrêt du conteneur"
terminer
exit "$CODE_SORTIE"
