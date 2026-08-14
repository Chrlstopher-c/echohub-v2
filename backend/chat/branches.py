"""Arbre des messages d'une conversation — logique pure, sans base, sans réseau, sans moteur.

Une conversation n'est plus une liste mais un arbre : chaque message porte l'identifiant de son
parent, et la vue courante est le CHEMIN qui descend d'une racine jusqu'à une feuille. Rejouer ou
éditer un message crée un frère sous le même parent ; rien n'est jamais réécrit ni supprimé.

Tout est pur ici : entrée, la liste des messages d'une conversation ; sortie, des chemins, des
feuilles, des variantes. C'est ce qui rend les branches testables sans base de données, comme le
planificateur l'est sans GPU. `depot` fait les lectures SQL, ce module fait les décisions.

Convention d'ordre : les messages entrent triés par `(cree_le, rowid)`. Les listes d'enfants
héritent donc de l'ordre de création, et « la variante la plus récente » est toujours la dernière.
"""

from __future__ import annotations

from collections.abc import Sequence

from loguru import logger

from backend.chat.modeles import MessageChat

# Borne dure de tous les parcours. Elle ne décrit aucune limite produit : elle garantit qu'un
# `parent_id` incohérent en base (cycle) ne fige pas une requête HTTP dans une boucle infinie.
PROFONDEUR_MAX = 100_000


def indexer(messages: Sequence[MessageChat]) -> dict[str, MessageChat]:
    """Messages par identifiant — l'index dont dépendent tous les parcours d'ancêtres."""
    return {message.id: message for message in messages}


def enfants_par_parent(messages: Sequence[MessageChat]) -> dict[str | None, list[MessageChat]]:
    """Enfants de chaque nœud, dans l'ordre de création. La clé `None` porte les racines."""
    groupes: dict[str | None, list[MessageChat]] = {}
    for message in messages:
        groupes.setdefault(message.parent_id, []).append(message)
    return groupes


def chemin_vers(messages: Sequence[MessageChat], feuille_id: str | None) -> list[MessageChat]:
    """Chemin racine → feuille. Vide si la feuille est inconnue : on ne devine pas un historique."""
    if feuille_id is None:
        return []
    par_id = indexer(messages)
    chemin: list[MessageChat] = []
    vus: set[str] = set()
    courant = par_id.get(feuille_id)
    while courant is not None and len(chemin) < PROFONDEUR_MAX:
        if courant.id in vus:
            logger.error("Cycle de parenté détecté sur le message {} — chemin tronqué.", courant.id)
            break
        vus.add(courant.id)
        chemin.append(courant)
        courant = par_id.get(courant.parent_id) if courant.parent_id is not None else None
    chemin.reverse()
    return chemin


def descendre(messages: Sequence[MessageChat], depart: str | None) -> str | None:
    """Feuille atteinte en suivant toujours l'enfant le plus récent depuis `depart`.

    Règle déterministe et unique : la branche affichée après une bascule est la plus récemment
    écrite sous le nœud choisi. Rendre `depart` lui-même quand il n'a pas d'enfant est le cas
    normal, pas un échec.
    """
    groupes = enfants_par_parent(messages)
    courant = depart
    for _ in range(PROFONDEUR_MAX):
        suivants = groupes.get(courant)
        if not suivants:
            return courant
        courant = suivants[-1].id
    logger.error("Descente interrompue à {} niveaux — parenté incohérente en base.", PROFONDEUR_MAX)
    return courant


def resoudre_feuille(messages: Sequence[MessageChat], feuille_enregistree: str | None) -> str | None:
    """Feuille réellement affichable : le pointeur enregistré s'il existe encore, sinon la plus récente.

    On redescend depuis le pointeur au lieu de le rendre tel quel : si un message a été écrit sous
    lui sans que le pointeur suive, la vue montre quand même la suite de la conversation plutôt
    qu'un historique tronqué. L'opération est neutre quand le pointeur est déjà une feuille.
    """
    if not messages:
        return None
    if feuille_enregistree is not None and feuille_enregistree in indexer(messages):
        return descendre(messages, feuille_enregistree)
    naturelle = descendre(messages, None)
    # Aucune racine lisible (parent orphelin) : le dernier message écrit reste la feuille la plus
    # défendable — mieux qu'un écran vide sur un historique qui existe bel et bien.
    return naturelle if naturelle is not None else messages[-1].id


def variantes(messages: Sequence[MessageChat], chemin: Sequence[MessageChat]) -> dict[str, list[str]]:
    """Frères de chaque message du chemin, lui compris, dans l'ordre de création."""
    groupes = enfants_par_parent(messages)
    return {
        message.id: [frere.id for frere in groupes.get(message.parent_id, [])]
        for message in chemin
    }
