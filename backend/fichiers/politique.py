"""Politique de validation des fichiers de conversation : quotas et types MIME acceptés.

Les deux quotas sont vérifiés AVANT toute écriture disque — c'est le premier filet. Le `setrlimit`
du processus confiné (`RLIMIT_FSIZE`, lot L2, hors périmètre ici) n'est qu'un second filet : un
processus tué par sa rlimit ne dit rien d'utilisable à l'utilisateur.

Le type MIME accepté est une liste blanche explicite, jamais dérivée du nom de fichier fourni : ce
nom vient de l'utilisateur ou du modèle, c'est une entrée non fiable. Le type MIME validé choisit
l'extension écrite sur le disque ; le nom fourni ne sert qu'à l'affichage (`nom_affiche`).
"""

from __future__ import annotations

from backend.fichiers.erreurs import FichierTropVolumineux, QuotaConversationDepasse, TypeMimeRefuse

# Non configurables via l'environnement pour l'instant : ce sont des bornes de sécurité, pas des
# chemins — la règle « tout dérive de la configuration » (`core/config.py`) porte sur les chemins,
# pas sur ces plafonds. À faire évoluer en réglages si un besoin réel apparaît.
TAILLE_MAX_FICHIER_OCTETS = 25 * 1024 * 1024  # 25 Mio par fichier
TAILLE_MAX_CUMULEE_OCTETS = 200 * 1024 * 1024  # 200 Mio cumulés par conversation

# Liste blanche : type MIME validé -> extension écrite sur le disque. Un type absent de cette table
# est refusé, quel que soit le nom de fichier fourni.
_MIME_AUTORISES: dict[str, str] = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "text/html": ".html",
    "text/css": ".css",
    "application/json": ".json",
    "application/pdf": ".pdf",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "application/zip": ".zip",
    "application/x-python": ".py",
    "text/x-python": ".py",
    "application/javascript": ".js",
    "text/javascript": ".js",
    "application/octet-stream": ".bin",
}


def valider_type_mime(type_mime_declare: str | None) -> str:
    """Valide le type MIME déclaré contre la liste blanche. Ne regarde jamais le nom du fichier.

    Les paramètres éventuels (`; charset=utf-8`) sont retirés avant comparaison : ils ne changent
    pas le type, seulement son encodage déclaré.
    """
    type_mime = (type_mime_declare or "").split(";")[0].strip().lower()
    if type_mime not in _MIME_AUTORISES:
        raise TypeMimeRefuse(
            f"Type MIME refusé : {type_mime or '(absent)'}",
            details={"type_mime": type_mime, "types_acceptes": sorted(_MIME_AUTORISES)},
        )
    return type_mime


def extension_pour(type_mime: str) -> str:
    """Extension imposée par le type MIME déjà validé — jamais par le nom fourni."""
    return _MIME_AUTORISES[type_mime]


def verifier_taille_fichier(taille_octets: int) -> None:
    """Lève si le fichier seul dépasse le plafond par fichier."""
    if taille_octets > TAILLE_MAX_FICHIER_OCTETS:
        raise FichierTropVolumineux(
            f"Fichier de {taille_octets} octets, plafond {TAILLE_MAX_FICHIER_OCTETS} octets.",
            remediation=f"Réduire le fichier sous {TAILLE_MAX_FICHIER_OCTETS // (1024 * 1024)} Mio.",
            details={"taille_octets": taille_octets, "plafond_octets": TAILLE_MAX_FICHIER_OCTETS},
        )


def verifier_quota_cumule(cumul_actuel_octets: int, taille_supplementaire_octets: int) -> None:
    """Lève si l'ajout ferait dépasser le plafond cumulé de la conversation."""
    total = cumul_actuel_octets + taille_supplementaire_octets
    if total > TAILLE_MAX_CUMULEE_OCTETS:
        raise QuotaConversationDepasse(
            f"Cumul {total} octets dépasserait le plafond {TAILLE_MAX_CUMULEE_OCTETS} octets.",
            remediation=f"La conversation a atteint {TAILLE_MAX_CUMULEE_OCTETS // (1024 * 1024)} Mio cumulés.",
            details={"cumul_octets": total, "plafond_octets": TAILLE_MAX_CUMULEE_OCTETS},
        )
