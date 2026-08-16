"""Génère les identifiants d'accès web d'EchoHub, à coller dans le `.env`.

EchoHub n'a aucune authentification applicative et son bac exécute du Python réel : tout accès
distant sans mot de passe revient à offrir l'exécution de code sur la machine. Ce script produit
les deux variables que `docker/entrypoint.sh` attend pour activer une authentification HTTP dans
nginx — sans toucher au système, sans droits administrateur.

Ce qui sort d'ici :

    ECHOHUB_AUTH_USER=<nom>
    ECHOHUB_AUTH_HASH=<empreinte crypt SHA-512, salée>

Le mot de passe en clair n'est affiché QU'UNE FOIS, à l'écran, et n'est écrit nulle part. Seule
son empreinte va dans le `.env`, qui n'est pas suivi par git. Un mot de passe perdu se remplace en
relançant ce script — il ne se retrouve pas.

Usage, depuis la racine du projet :

    docker compose exec echohub /app/backend/.venv/bin/python docker/outils-acces.py
    docker compose exec echohub /app/backend/.venv/bin/python docker/outils-acces.py --nom chris
"""

from __future__ import annotations

import argparse
import crypt
import secrets
import string

# 20 caractères d'un alphabet sans ambiguïté visuelle (ni O/0, ni l/1/I) : ce mot de passe se
# recopie à la main sur un téléphone, et une confusion coûterait un aller-retour inutile.
ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "O0lI1")
LONGUEUR = 20


def engendrer(nom: str) -> tuple[str, str]:
    """Mot de passe aléatoire et son empreinte crypt SHA-512 salée, lisible par nginx."""
    mot_de_passe = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR))
    empreinte = crypt.crypt(mot_de_passe, crypt.mksalt(crypt.METHOD_SHA512))
    return mot_de_passe, empreinte


def principal() -> None:
    analyseur = argparse.ArgumentParser(description="Identifiants d'accès web EchoHub")
    analyseur.add_argument("--nom", default="echohub", help="nom d'utilisateur (défaut : echohub)")
    arguments = analyseur.parse_args()

    mot_de_passe, empreinte = engendrer(arguments.nom)

    print("\n=== À COLLER DANS LE FICHIER .env, PUIS `docker compose up -d` ===\n")
    print(f"ECHOHUB_AUTH_USER={arguments.nom}")
    print(f"ECHOHUB_AUTH_HASH={empreinte}")
    print("\n=== IDENTIFIANTS DE CONNEXION — notés maintenant, ils ne réapparaîtront pas ===\n")
    print(f"  utilisateur : {arguments.nom}")
    print(f"  mot de passe : {mot_de_passe}")
    print(
        "\nLe mot de passe n'est stocké nulle part : le `.env` ne reçoit que son empreinte salée.\n"
        "Perdu, il se remplace en relançant ce script — il ne se retrouve pas.\n"
    )


if __name__ == "__main__":
    principal()
