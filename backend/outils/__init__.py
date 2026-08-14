"""Domaine `outils` — le harnais : ce que le modèle peut faire, et ce qu'on lui dit pouvoir faire.

Interface publique. Les autres domaines importent d'ici et jamais d'un sous-module.

Le domaine existe pour supprimer un écart mesuré : sans outils déclarés, les modèles chargés ici
annoncent des capacités qu'ils n'ont pas et fabriquent des résultats. Il tient donc ensemble deux
choses qui doivent rester cohérentes — la liste réelle des outils exécutables, et le texte qui la
décrit au modèle. Une seule source, lue aux deux endroits.

Découpe interne, dans l'ordre des dépendances :

    contrat         forme d'un outil et de son résultat
    recherche_web   premier outil, adossé au domaine `recherche`
    registre        outils disponibles et exécution d'un appel
    socle           prompt système posé avant celui de la conversation
"""

from backend.outils.contrat import DescriptionOutil, Outil, ResultatOutil
from backend.outils.registre import descriptions, disponibles, executer, format_moteur
from backend.outils.socle import composer, construire


def prompt_socle() -> str:
    """Socle correspondant aux outils réellement enregistrés à cet instant."""
    return construire(descriptions())


def prompt_systeme(prompt_conversation: str) -> str:
    """Prompt système complet : socle d'abord, prompt de la conversation ensuite.

    C'est le seul point d'entrée que la génération doit utiliser. Composer ailleurs ferait exister
    un chemin où le socle est oublié — et ce chemin serait justement celui où le modèle affabule.
    """
    return composer(prompt_socle(), prompt_conversation)


__all__ = [
    "DescriptionOutil",
    "Outil",
    "ResultatOutil",
    "descriptions",
    "disponibles",
    "executer",
    "format_moteur",
    "prompt_socle",
    "prompt_systeme",
]
