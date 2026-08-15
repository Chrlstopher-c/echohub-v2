# EchoHub v2 — image conteneur avec accélération GPU NVIDIA.
#
# Chaque contrainte de ce fichier est mesurée, jamais déduite : la référence est
# COMPATIBILITE-GPU.md. Ne rien modifier ici sans une mesure qui contredit la mesure d'origine.
#
# CUDA 12.8.0 : plancher — premier Toolkit qui connaît sm_120 (Blackwell, RTX 5080 cible).
# Variante `devel` obligatoire : `runtime` n'embarque ni nvcc ni les en-têtes CUDA, donc aucune
# compilation de llama-cpp-python possible.
FROM nvidia/cuda:12.8.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Ubuntu 22.04 fournit Python 3.10, la version visée par ARCHITECTURE.md (imposée par
# llama-cpp-python et vLLM, pas choisie).
#
# `unzip` n'est pas décoratif : l'installeur Bun télécharge une archive zip et échoue sans lui.
# `nginx` sert le frontend statique et proxifie /api — il n'y a pas de coquille Tauri ici.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip python3-dev \
        build-essential cmake ninja-build git curl unzip ca-certificates \
        nginx \
    && rm -rf /var/lib/apt/lists/*

# Bun — runtime JS/TS du projet (jamais npm ni node en direct).
ENV BUN_INSTALL=/usr/local/bun
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="${BUN_INSTALL}/bin:${PATH}"

WORKDIR /app

# --- Backend Python ------------------------------------------------------------------------
# Venv isolé : les dépendances de vLLM (torch, CUDA 13) entrent en conflit avec celles du
# backend, elles iront dans un venv séparé géré à l'exécution par le domaine `engines`.
COPY backend/requirements.txt backend/requirements.txt
RUN python3 -m venv /app/backend/.venv
ENV PATH="/app/backend/.venv/bin:${PATH}"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r backend/requirements.txt

# Recompilation de llama-cpp-python depuis les sources — la couche la plus longue du build,
# volontairement placée avant toute copie de code pour qu'une modification applicative ne
# l'invalide jamais.
#
# `--no-binary` est obligatoire : le wheel PyPI installé juste au-dessus est CPU-only. Sans lui
# tout « fonctionne » et rien ne touche le GPU — panne silencieuse, la pire catégorie.
#
# CMAKE_CUDA_ARCHITECTURES=86;120 : sm_86 pour la machine de développement (RTX 3060), sm_120
# pour la cible (RTX 5080). CMake convertit automatiquement 120 en 120a.
#
# GGML_CUDA_FORCE_CUBLAS=ON n'est PAS cosmétique — que personne ne le retire pour « gagner de
# la perf ». Sans ce flag, nvcc de CUDA 12.8 SEGFAULTE en compilant les kernels MMQ de ggml
# (template-instances/mmq-instance-q2_k.cu) pour compute_120a. C'est un bug du compilateur, pas
# du code de ggml, et ce n'est pas un OOM déguisé (vérifié). Le flag route les multiplications
# quantifiées vers cuBLAS et évite de compiler les kernels fautifs.
# Issues amont : llama.cpp#18331 et llama.cpp#24399.
# Coût non mesuré : perte de débit possible face aux kernels MMQ natifs. À réévaluer — par une
# mesure — quand le bug nvcc sera corrigé en amont.
ENV CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=86;120 -DGGML_CUDA_FORCE_CUBLAS=ON" \
    FORCE_CMAKE=1
RUN pip install --no-cache-dir --force-reinstall --no-binary llama-cpp-python llama-cpp-python

# --- Frontend (build web statique) ----------------------------------------------------------
# Dépendances d'abord, sources ensuite : une modification de composant ne relance pas l'install.
# Le glob sur bun.lock tolère son absence au tout début du projet.
COPY frontend/package.json frontend/bun.lock* frontend/
RUN cd frontend \
    && if [ -f bun.lock ]; then bun install --frozen-lockfile; else bun install; fi

COPY frontend/ frontend/
# `bun run build` = `tsc && vite build`. La v1 contournait trois erreurs TypeScript en
# construisant avec `vite` seul, ce qui les rendait invisibles pour toujours. Ici l'échec de
# `tsc` doit casser le build : c'est le seul endroit du projet qui garantit que le typage passe.
RUN cd frontend && bun run build

# --- Backend applicatif ---------------------------------------------------------------------
# Copié en dernier des sources : c'est ce qui change le plus souvent.
COPY backend/ backend/

# --- Reverse proxy et point d'entrée --------------------------------------------------------
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Stockage persistant. Ces deux chemins sont montés sur des volumes nommés par
# docker-compose.yml : tout ce qui est écrit ailleurs disparaît au prochain `docker compose up`.
#   MODELS_DIR      → modèles GGUF/AWQ téléchargés
#   XDG_DATA_HOME   → base SQLite, configuration et journaux applicatifs
ENV MODELS_DIR=/data/models \
    XDG_DATA_HOME=/data/user

# 80    : interface web servie par nginx (frontend statique + proxy /api)
# 37921 : API FastAPI exposée directement, pour le débogage sans passer par le proxy — distinct
#         du port par défaut de la v1 (37821), qui peut tourner sur le même hôte.
EXPOSE 80 37921

ENTRYPOINT ["/entrypoint.sh"]
