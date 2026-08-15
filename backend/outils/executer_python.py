"""Outil `executer_python` — exécution réelle de code Python, confinée, un bac par conversation.

Suit le contrat commun (`backend/outils/contrat.py`) : reçoit des arguments validés et le
`ContexteExecution` de l'appelant, rend un texte destiné à repartir dans le contexte du modèle.
Toute la mécanique de confinement vit dans `bac_a_sable.py` ; tout le balayage post-exécution vit
dans `balayage_bac.py`. Ce module ne fait que les relier et mettre en forme le résultat.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from backend.outils.bac_a_sable import LIMITES_REELLES_TEXTE, executer_code_confine
from backend.outils.balayage_bac import balayer_et_enregistrer, etat_bac
from backend.outils.contrat import ContexteExecution, DescriptionOutil, Outil

NOM = "executer_python"

# Un résultat interminable mangerait le contexte du modèle sans rien apporter de plus qu'un
# résultat tronqué et lisible : `ResultatOutil.tronque()` s'applique déjà en aval (registre.py),
# cette borne locale évite seulement de construire un texte énorme avant d'y arriver.
LONGUEUR_SORTIE_MAX = 4_000

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "Code Python à exécuter. Le répertoire de travail est le bac de cette "
            "conversation : tout fichier écrit avec un chemin relatif y apparaît et devient un "
            "fichier de la conversation, visible par l'utilisateur.",
        },
    },
    "required": ["code"],
}

DESCRIPTION = DescriptionOutil(
    nom=NOM,
    description=(
        "Exécute du code Python réellement, dans un processus confiné et borné en temps, mémoire "
        "et nombre de processus. Utiliser pour calculer, transformer des données ou produire un "
        "fichier (image, CSV, texte…) plutôt que d'inventer un résultat. Le code n'a pas accès à "
        "Internet ni aux fichiers d'autres conversations."
    ),
    parametres=_SCHEMA,
)


def _tronque(texte: str) -> str:
    if len(texte) <= LONGUEUR_SORTIE_MAX:
        return texte
    return f"{texte[:LONGUEUR_SORTIE_MAX]}\n[sortie tronquée à {LONGUEUR_SORTIE_MAX} caractères]"


def _formater(resultat: Any, fichiers: list[Any]) -> str:
    lignes = [f"Code de retour : {resultat.code_retour} (durée : {resultat.duree_s:.2f} s)"]
    if resultat.tue_par_filet_securite:
        lignes.append("Processus tué : dépassement du temps autorisé (temps processeur ou filet de sécurité).")
    if resultat.sortie.strip():
        lignes.append(f"Sortie standard :\n{_tronque(resultat.sortie)}")
    if resultat.erreur.strip():
        lignes.append(f"Sortie d'erreur :\n{_tronque(resultat.erreur)}")
    if fichiers:
        noms = ", ".join(f"{f.nom_affiche} (id {f.id})" for f in fichiers)
        lignes.append(f"Fichier(s) produit(s), déposés dans la conversation : {noms}")
    return "\n\n".join(lignes)


async def executer(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
    """Exécute le code demandé dans le bac de `contexte`, balaie, rend un texte pour le modèle.

    Le sous-processus est bloquant (rlimits + `subprocess.run`) : il tourne sur un thread séparé
    (`asyncio.to_thread`) pour ne jamais geler la boucle asyncio pendant les quelques secondes
    d'exécution.
    """
    code = str(arguments.get("code", "")).strip()
    if not code:
        return "Échec : aucun code fourni. Rappeler l'outil avec un argument « code » non vide."

    avant = etat_bac(contexte.racine_bac)
    resultat = await asyncio.to_thread(executer_code_confine, code, contexte.racine_bac)
    fichiers = balayer_et_enregistrer(contexte.conversation_id, contexte.racine_bac, avant)
    logger.info(
        "executer_python : code_retour={} durée={:.2f}s fichiers_produits={}",
        resultat.code_retour, resultat.duree_s, len(fichiers),
    )
    return _formater(resultat, fichiers)


OUTIL = Outil(description=DESCRIPTION, executer=executer)

__all__ = ["OUTIL", "LIMITES_REELLES_TEXTE"]
