"""Service d'exécution de l'atelier — reçoit une commande ou du code, l'exécute root, rend le résultat.

C'est le seul processus qui écoute dans le conteneur atelier. Il n'est JAMAIS publié sur l'hôte :
Compose l'expose uniquement sur le réseau interne de la pile, où seul le backend l'atteint. Un jeton
partagé (`ATELIER_JETON`) garde chaque route d'exécution — sans lui, n'importe quel conteneur du
réseau exécuterait du shell root ici. Le repli est FERMÉ : jeton absent de l'environnement =
exécution refusée, jamais ouverte par défaut.

L'agent est root dans ce conteneur, avec réseau et PATH complet, et c'est voulu : l'isolation vient
de la frontière du conteneur (aucun chemin de l'hôte monté, ressources bornées par Compose), pas de
privilèges abaissés. Chaque conversation travaille dans `/workspace/<sous_dossier>`, un volume
partagé avec le backend — un fichier produit ici est balayé et rattaché à la conversation.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

# Racine des espaces de travail, montée sur le volume partagé avec le backend. Chaque conversation a
# son sous-dossier ; l'agent peut se déplacer ailleurs dans le conteneur, mais son point de départ
# est toujours là.
WORKSPACE = Path(os.environ.get("ATELIER_WORKSPACE", "/workspace"))

# Sortie bornée : une compilation bavarde ou un `apt install` verbeux dépasse vite le raisonnable.
# Le backend retronque pour le modèle ; cette borne-ci protège la mémoire du service.
MAX_SORTIE_OCTETS = 1_000_000

_JETON = os.environ.get("ATELIER_JETON", "")


class RequeteCommande(BaseModel):
    commande: str = Field(min_length=1)
    sous_dossier: str = Field(min_length=1)
    timeout_s: int = Field(gt=0, le=3600)


class RequetePython(BaseModel):
    code: str = Field(min_length=1)
    sous_dossier: str = Field(min_length=1)
    timeout_s: int = Field(gt=0, le=3600)


class Resultat(BaseModel):
    code_retour: int
    sortie: str
    erreur: str
    duree_s: float
    tue: bool


def verifier_jeton(x_atelier_jeton: str = Header(default="")) -> None:
    """Repli fermé : sans jeton configuré, ou jeton faux, l'exécution est refusée."""
    if not _JETON or x_atelier_jeton != _JETON:
        raise HTTPException(status_code=401, detail="Jeton d'atelier absent ou invalide.")


def _dossier_travail(sous_dossier: str) -> Path:
    """Résout `/workspace/<sous_dossier>`, refuse toute sortie de la racine, crée le dossier.

    Le sous-dossier vient du backend (donc de confiance), mais il est validé quand même : un `..`
    ou un chemin absolu ne doit jamais faire écrire hors du volume partagé.
    """
    cible = (WORKSPACE / sous_dossier).resolve()
    if cible != WORKSPACE.resolve() and WORKSPACE.resolve() not in cible.parents:
        raise HTTPException(status_code=400, detail=f"Sous-dossier hors workspace : « {sous_dossier} ».")
    cible.mkdir(parents=True, exist_ok=True)
    return cible


def _tronquer(flux: str | bytes | None) -> str:
    texte = flux.decode("utf-8", "replace") if isinstance(flux, bytes) else (flux or "")
    if len(texte) <= MAX_SORTIE_OCTETS:
        return texte
    return f"{texte[:MAX_SORTIE_OCTETS]}\n[sortie tronquée à {MAX_SORTIE_OCTETS} octets]"


def _lancer(argv: list[str], cwd: Path, timeout_s: int) -> Resultat:
    """Lance `argv` dans `cwd`, borné en temps, et rend le résultat. Ne lève jamais vers l'appelant."""
    debut = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        logger.warning("Commande tuée après {} s dans {} : {}", timeout_s, cwd.name, argv[0])
        return Resultat(code_retour=-1, sortie=_tronquer(exc.stdout),
                        erreur=f"{_tronquer(exc.stderr)}\n[Processus tué : délai de {timeout_s}s dépassé]",
                        duree_s=time.monotonic() - debut, tue=True)
    except OSError as exc:
        logger.error("Lancement impossible ({}) : {}", argv[0], exc)
        return Resultat(code_retour=-1, sortie="", erreur=f"Lancement impossible : {exc}",
                        duree_s=time.monotonic() - debut, tue=False)
    return Resultat(code_retour=proc.returncode, sortie=_tronquer(proc.stdout),
                    erreur=_tronquer(proc.stderr), duree_s=time.monotonic() - debut, tue=False)


def _executer_python(code: str, cwd: Path, timeout_s: int) -> Resultat:
    """Écrit le code dans un fichier temporaire HORS workspace et le lance.

    Passer par un fichier évite la limite de taille d'argument d'un `python3 -c`, et le poser hors
    du workspace évite qu'il soit balayé comme un fichier produit par la conversation. Sans `-I` :
    l'atelier a un vrai environnement, un paquet installé par `pip` doit être visible.
    """
    fichier = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
    try:
        fichier.write(code)
        fichier.close()
        return _lancer(["python3", fichier.name], cwd, timeout_s)
    finally:
        Path(fichier.name).unlink(missing_ok=True)


app = FastAPI(title="EchoHub — atelier d'exécution")


@app.get("/sante")
def sante() -> dict[str, str]:
    """Sonde ouverte (pas de jeton) : sert au healthcheck Docker via curl localhost."""
    return {"statut": "ok", "jeton_configure": "oui" if _JETON else "non"}


@app.post("/executer/commande", response_model=Resultat, dependencies=[Depends(verifier_jeton)])
def executer_commande(requete: RequeteCommande) -> Resultat:
    cwd = _dossier_travail(requete.sous_dossier)
    logger.info("commande dans {} (timeout {}s)", requete.sous_dossier, requete.timeout_s)
    return _lancer(["bash", "-lc", requete.commande], cwd, requete.timeout_s)


@app.post("/executer/python", response_model=Resultat, dependencies=[Depends(verifier_jeton)])
def executer_python(requete: RequetePython) -> Resultat:
    cwd = _dossier_travail(requete.sous_dossier)
    logger.info("python dans {} (timeout {}s)", requete.sous_dossier, requete.timeout_s)
    return _executer_python(requete.code, cwd, requete.timeout_s)


if __name__ == "__main__":
    if not _JETON:
        logger.warning("ATELIER_JETON absent : toutes les exécutions seront refusées (repli fermé).")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
