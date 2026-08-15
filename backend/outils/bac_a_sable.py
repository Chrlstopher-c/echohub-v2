"""Lanceur du processus Python confiné — un bac à sable par conversation (plan d'exécution, 2.6).

Le confinement tient en trois idées, dans cet ordre impératif à l'intérieur du processus enfant,
juste après le `fork` et avant l'`exec` (`_preexec`) :

    1. poser les limites de ressources (`resource.setrlimit`) ;
    2. changer de groupe (`setgid`) ;
    3. changer d'utilisateur (`setuid`) — en DERNIER, parce que c'est irréversible : une fois cet
       appel passé, le processus ne peut plus revenir root pour corriger un oubli.

`SANDBOX_UID`/`SANDBOX_GID` sont l'utilisateur non privilégié créé par le `Dockerfile` (identifiant
fixe, sans shell, sans dossier personnel utilisable). Le changement ne s'opère que si le processus
appelant est root (`os.getuid() == 0`) : en développement, les tests tournent déjà sous un utilisateur
non privilégié, `setuid` vers un uid arbitraire y échouerait — et n'y sert à rien, l'isolement racine
existe déjà. C'est le conteneur, où le backend tourne en root, qui a besoin de cette bascule.

Coupure réseau — mesurée, pas supposée. `unshare(CLONE_NEWNET)` exige `CAP_SYS_ADMIN` dans l'espace
de noms courant. Mesuré dans `echohub:v2` (2026-08-15, root, sans capacité ajoutée) :

    unshare(CLONE_NEWNET) ret=-1 errno=1 (EPERM), duree_ms≈0.02

Docker Compose ne déclare aucun `cap_add` pour ce service : le jeu de capacités par défaut exclut
`CAP_SYS_ADMIN`. Ce n'est donc pas une question de coût de démarrage — la mesure ne dit même pas
« c'est lent », elle dit « c'est refusé ». Contourner avec un espace de noms utilisateur non privilégié
(`unshare --user --net`) est possible en théorie, mais cela ouvrirait indépendamment la porte aux
espaces de noms utilisateur non privilégiés dans ce conteneur — une surface d'attaque connue pour des
échappées de conteneur, et un arbitrage qui dépasse ce lot. Décision : **le réseau n'est PAS coupé**.
C'est écrit ici et dans `LIMITES_REELLES_TEXTE`, pas caché dans un commentaire que personne ne lira.
"""

from __future__ import annotations

import os
import resource
import subprocess
import time
from pathlib import Path

from loguru import logger
from pydantic import BaseModel

# Utilisateur non privilégié créé par le Dockerfile — identifiant fixe (voir `Dockerfile`,
# utilisateur `echohub-bac`). Ce n'est pas un chemin : comme les quotas de `fichiers/politique.py`,
# c'est une borne de sécurité, elle ne dérive pas de la configuration d'environnement.
SANDBOX_UID = 65532
SANDBOX_GID = 65532

# --- Limites de ressources (RLIMIT_*) ----------------------------------------------------------
# Temps processeur : suffisant pour un script de quelques secondes, pas pour attendre un réseau.
LIMITE_CPU_SECONDES = 5
# Mémoire adressable : le socle de l'interpréteur Python tient sous 40 Mo mesurés ; 512 Mo laisse
# une vraie marge de calcul sans autoriser un processus à épuiser la RAM du conteneur.
LIMITE_MEMOIRE_OCTETS = 512 * 1024 * 1024
# Taille de fichier : au-delà du quota par fichier du magasin (25 Mio, `fichiers/politique.py`),
# volontairement plus large pour que ce soit le balayage — pas la rlimit — qui explique le refus
# d'un fichier entre 25 et 64 Mio. Au-delà de 64 Mio, l'écriture échoue au niveau du système.
LIMITE_TAILLE_FICHIER_OCTETS = 64 * 1024 * 1024
# Nombre de processus : cette rlimit est comptée par le NOYAU sur la totalité de l'UID, pas par
# exécution — un fork-bomb doit mourir, un script qui lance quelques sous-processus doit passer.
LIMITE_PROCESSUS = 32
# Descripteurs ouverts : large pour l'interpréteur lui-même (imports, stdio) et les fichiers que
# le script ouvre légitimement, borné pour qu'un `while True: open(...)` échoue vite.
LIMITE_DESCRIPTEURS = 64

# Filet de sécurité du côté appelant, distinct de RLIMIT_CPU : une boucle qui dort (`time.sleep`)
# ne consomme aucun temps processeur et échapperait donc à RLIMIT_CPU seul. Ce timeout mesure le
# temps RÉEL écoulé et tue le processus si jamais il dépasse largement le plafond CPU fixé.
TIMEOUT_SECURITE_SECONDES = 20

# Environnement transmis au processus confiné : jamais l'environnement du backend tel quel, qui
# porte des secrets (HF_TOKEN, l'URL interne de SearXNG). Un script exécuté par un modèle est une
# entrée non fiable ; il n'a besoin de rien de plus qu'un PATH minimal pour trouver l'interpréteur.
_ENVIRONNEMENT_CONFINE: dict[str, str] = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
}

LIMITES_REELLES_TEXTE = (
    "Le code Python s'exécute dans un processus séparé, sous un utilisateur non privilégié "
    "(jamais administrateur), et il écrit uniquement dans le bac de cette conversation — ce qu'il y "
    "produit devient un fichier de la conversation. Il est borné en temps processeur, en mémoire, "
    "en taille de fichier écrit, en nombre de processus et en descripteurs ouverts. "
    "Ce qui N'EST PAS garanti : sans isolation du système de fichiers (les outils nécessaires ne "
    "sont pas disponibles dans ce conteneur), ce processus voit en lecture le système de fichiers du "
    "conteneur au-delà de son bac ; et le réseau n'est pas coupé — la coupure a été mesurée "
    "impossible sans élargir les droits du conteneur au-delà de ce qui a été décidé ici."
)


class ResultatExecution(BaseModel):
    """Ce que le processus confiné a produit — jamais levé en exception, toujours rendu."""

    sortie: str
    erreur: str
    code_retour: int
    duree_s: float
    tue_par_filet_securite: bool


def _preexec() -> None:
    """Exécuté dans l'enfant, entre le `fork` et l'`exec` — jamais dans le processus appelant.

    Ordre imposé par le plan d'exécution (2.6) : rlimits, puis `setgid`, puis `setuid`. `setuid`
    est irréversible, il vient donc en dernier — inverser l'ordre laisserait une fenêtre où le
    processus est root ET déjà limité en rien.
    """
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITE_CPU_SECONDES, LIMITE_CPU_SECONDES))
    resource.setrlimit(resource.RLIMIT_AS, (LIMITE_MEMOIRE_OCTETS, LIMITE_MEMOIRE_OCTETS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITE_TAILLE_FICHIER_OCTETS, LIMITE_TAILLE_FICHIER_OCTETS))
    resource.setrlimit(resource.RLIMIT_NPROC, (LIMITE_PROCESSUS, LIMITE_PROCESSUS))
    resource.setrlimit(resource.RLIMIT_NOFILE, (LIMITE_DESCRIPTEURS, LIMITE_DESCRIPTEURS))
    if os.getuid() == 0:
        os.setgid(SANDBOX_GID)
        os.setuid(SANDBOX_UID)


def preparer_bac(racine_bac: Path) -> None:
    """Crée le bac s'il n'existe pas et le rend écrivable par l'utilisateur confiné.

    Le processus appelant (le backend) tourne en root dans le conteneur : c'est lui qui doit céder
    la propriété du dossier, l'utilisateur confiné ne peut pas se l'attribuer lui-même. En
    développement (appelant déjà non privilégié), le `chown` est sauté : il échouerait, et il ne
    sert à rien puisque le processus confiné n'est alors jamais un autre utilisateur.
    """
    racine_bac.mkdir(parents=True, exist_ok=True)
    if os.getuid() == 0:
        os.chown(racine_bac, SANDBOX_UID, SANDBOX_GID)
        os.chmod(racine_bac, 0o700)


def executer_code_confine(code: str, racine_bac: Path) -> ResultatExecution:
    """Lance `python3 -I -c <code>` dans le bac, confiné, et rend ce qui a été produit.

    Bloquant : l'appelant (`backend/outils/executer_python.py`) le pousse sur un thread pour ne
    pas geler la boucle asyncio pendant l'exécution. `-I` (mode isolé) ignore `PYTHONPATH` et le
    site-packages utilisateur — un script d'un modèle ne doit dépendre d'aucun état ambiant.
    """
    preparer_bac(racine_bac)
    debut = time.monotonic()
    try:
        processus = subprocess.run(
            ["python3", "-I", "-c", code],
            cwd=racine_bac,
            env=_ENVIRONNEMENT_CONFINE,
            preexec_fn=_preexec,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECURITE_SECONDES,
        )
    except subprocess.TimeoutExpired as exc:
        duree = time.monotonic() - debut
        logger.warning("Exécution Python confinée tuée par le filet de sécurité ({} s).", TIMEOUT_SECURITE_SECONDES)
        sortie = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        erreur = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
        return ResultatExecution(
            sortie=sortie,
            erreur=f"{erreur}\n[Processus tué : dépassement du filet de sécurité de {TIMEOUT_SECURITE_SECONDES}s]",
            code_retour=-1,
            duree_s=duree,
            tue_par_filet_securite=True,
        )
    duree = time.monotonic() - debut
    return ResultatExecution(
        sortie=processus.stdout,
        erreur=processus.stderr,
        code_retour=processus.returncode,
        duree_s=duree,
        tue_par_filet_securite=False,
    )
