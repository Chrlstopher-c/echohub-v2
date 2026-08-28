# EchoHub — atelier d'exécution.
#
# Image de DÉVELOPPEMENT complète : l'agent (le modèle, via les outils du backend) y est root, avec
# réseau et un vrai toolchain. Il installe le reste lui-même à l'exécution (`apt-get`, `pip`). Ce
# Dockerfile ne pose donc que le socle — surtout PAS l'outillage qu'on veut prouver installable au
# fil de l'eau (nasm, par exemple, reste absent : le modèle doit pouvoir l'ajouter).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Socle de dev : shell, réseau, compilateurs, python, node, git. `sudo` est présent par confort
# même si l'agent est déjà root. `nasm` est VOLONTAIREMENT absent — c'est le cas de preuve.
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash sudo ca-certificates curl wget git unzip \
        build-essential make cmake pkg-config binutils \
        python3 python3-pip python3-venv python3-dev \
        nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 24.04 marque l'environnement Python comme « externally managed » (PEP 668) et refuse
# `pip install` global sans `--break-system-packages`. L'agent, lui, tape `pip install <pkg>` sans
# ce drapeau : retirer le marqueur lui rend ce réflexe fonctionnel. Assumé — l'atelier est jetable
# et isolé, ce n'est pas un système à préserver.
RUN rm -f /usr/lib/python3*/EXTERNALLY-MANAGED

# Dépendances du service d'exécution (pas de l'agent). `--break-system-packages` par cohérence avec
# le marqueur retiré ci-dessus.
WORKDIR /opt/atelier
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY serveur.py .

# Sonde locale, jamais publiée sur l'hôte : le healthcheck Docker interroge la route ouverte /sante.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -fsS http://localhost:8080/sante || exit 1

EXPOSE 8080

CMD ["python3", "serveur.py"]
