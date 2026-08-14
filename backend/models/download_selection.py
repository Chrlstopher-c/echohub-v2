"""Quoi télécharger dans un dépôt, et combien cela pèse réellement.

Toutes les fonctions de ce module sont pures : elles prennent l'inventaire du dépôt et rendent une
décision. Aucune n'ouvre de connexion ni n'écrit sur le disque, ce qui les rend vérifiables sans
réseau — condition posée par `ARCHITECTURE.md` pour tout ce qui décide à la place de l'utilisateur.

Deux décisions y sont prises, et les deux évitent de télécharger des dizaines de gigaoctets pour
rien : ce qu'on écarte d'un dépôt, et ce qu'on refuse de deviner quand plusieurs quantifications
cohabitent.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from backend.core.errors import ModeleIntrouvable, TelechargementEchoue
from backend.models.discovery import FichierDepot
from backend.models.storage import octets_fichier, octets_fragments, taille_reelle_octets

# Écartés systématiquement : documentation et poids d'origine, jamais utiles à l'inférence.
MOTIFS_TOUJOURS_IGNORES = ("*.md", "original/*")
# Écartés seulement si le dépôt propose des safetensors, sinon ce sont les seuls poids disponibles.
EXTENSIONS_POIDS_REDONDANTS = (".bin", ".pth", ".pt", ".h5", ".msgpack", ".ckpt")

# Un GGUF trop gros pour un seul fichier est publié en parts numérotées, selon la convention
# llama.cpp `<base>-00001-of-00003.gguf`. Ce sont les morceaux d'UN modèle, pas trois modèles :
# n'en prendre qu'un donne un fichier sans en-tête exploitable, que le registre écarte et que le
# moteur ne peut pas charger.
#
# Constaté le 2026-08-14 : un téléchargement annoncé « terminé » n'avait rapporté que la part 2
# sur 2 de Qwen3-Coder-30B — sans gabarit de conversation, donc inutilisable.
MOTIF_PART_GGUF = re.compile(r"^(?P<base>.+)-(?P<rang>\d{5})-of-(?P<total>\d{5})\.gguf$", re.IGNORECASE)


def parts_du_meme_modele(cible: str, fichiers: list[FichierDepot]) -> list[str]:
    """Toutes les parts du modèle dont `cible` fait partie, `cible` comprise, triées par rang.

    Rend `[cible]` quand ce n'est pas un fichier en parts — le cas courant, qui doit rester simple.
    Les parts absentes du dépôt ne sont pas inventées : on ne retient que ce qui y existe vraiment.
    """
    trouve = MOTIF_PART_GGUF.match(cible)
    if trouve is None:
        return [cible]
    base, total = trouve.group("base"), trouve.group("total")
    freres = [
        fichier.nom
        for fichier in fichiers
        if (autre := MOTIF_PART_GGUF.match(fichier.nom)) is not None
        and autre.group("base") == base
        and autre.group("total") == total
    ]
    return sorted(freres) or [cible]


def motifs_ignores(fichiers: list[FichierDepot]) -> list[str]:
    """Motifs d'exclusion déduits de la liste **réelle** des fichiers du dépôt.

    Beaucoup de dépôts publient les mêmes poids en safetensors et en `.bin` PyTorch. Les prendre
    tous les deux double la taille du téléchargement sans rien apporter — mais un dépôt qui n'a que
    des `.bin` doit continuer de fonctionner, d'où une décision prise sur le contenu et non sur un
    motif figé.
    """
    noms = [fichier.nom.lower() for fichier in fichiers]
    motifs = list(MOTIFS_TOUJOURS_IGNORES)
    if any(nom.endswith(".safetensors") for nom in noms):
        motifs.extend(f"*{extension}" for extension in EXTENSIONS_POIDS_REDONDANTS)
    return motifs


def est_ignore(nom: str, motifs: list[str]) -> bool:
    """Vrai si ce nom de fichier tombe sous l'un des motifs d'exclusion."""
    return any(fnmatch.fnmatch(nom, motif) for motif in motifs)


def octets_totaux(fichiers: list[FichierDepot], cible: str | None, motifs: list[str]) -> int | None:
    """Total annoncé par le Hub pour ce que l'on va effectivement chercher.

    `None` dès qu'une taille manque : un pourcentage calculé sur un total incomplet vaut moins que
    pas de pourcentage du tout.
    """
    if cible is not None:
        # Le total couvre TOUTES les parts du modèle, pas seulement celle qui a été cliquée :
        # sinon la barre annonce « terminé » à la première part et masque un modèle incomplet.
        attendus = set(parts_du_meme_modele(cible, fichiers))
        retenus = [fichier for fichier in fichiers if fichier.nom in attendus]
    else:
        retenus = [fichier for fichier in fichiers if not est_ignore(fichier.nom, motifs)]
    if not retenus or any(fichier.taille_octets is None for fichier in retenus):
        return None
    return sum(fichier.taille_octets or 0 for fichier in retenus)


def resoudre_cible(depot: str, fichier: str | None, fichiers: list[FichierDepot]) -> str | None:
    """Fichier à récupérer, ou `None` pour prendre le dépôt entier.

    Un dépôt GGUF héberge couramment huit quantifications du même modèle. Les télécharger toutes
    parce qu'aucune n'a été choisie représenterait des dizaines de gigaoctets pour rien : on refuse,
    en listant les possibilités plutôt qu'en en choisissant une à la place de l'utilisateur.
    """
    if fichier is not None:
        if fichiers and all(candidat.nom != fichier for candidat in fichiers):
            raise ModeleIntrouvable(
                f"Le fichier « {fichier} » n'existe pas dans {depot}.",
                details={"depot": depot, "fichier": fichier},
            )
        return fichier

    gguf = [candidat.nom for candidat in fichiers if candidat.nom.lower().endswith(".gguf")]
    autres_poids = any(candidat.nom.lower().endswith(".safetensors") for candidat in fichiers)
    if not gguf or autres_poids:
        return None
    if len(gguf) == 1:
        return gguf[0]
    raise TelechargementEchoue(
        f"{depot} propose {len(gguf)} fichiers GGUF : il faut en choisir un.",
        remediation="Sélectionner une quantification dans la fiche du dépôt avant de lancer le téléchargement.",
        details={"depot": depot, "fichiers": sorted(gguf)},
    )


def octets_recus(dossier: Path, fichier: str | None) -> int:
    """Octets réellement présents sur le disque pour ce téléchargement.

    Pour un fichier unique on mesure ce fichier et les fragments en cours, jamais le dossier
    entier : le même dépôt peut déjà héberger une autre quantification, dont les octets n'ont rien
    à voir avec la progression en cours.
    """
    if fichier is None:
        return taille_reelle_octets(dossier)
    return octets_fichier(dossier / fichier) + octets_fragments(dossier)
