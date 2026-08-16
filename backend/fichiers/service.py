"""Orchestration du domaine `fichiers` : dépose et sert un fichier de conversation.

Un seul mécanisme pour les deux origines (`utilisateur`, `modele`) : ce module n'expose qu'une
opération d'écriture, `deposer_fichier`, distinguée par son paramètre `origine` — jamais deux
chemins de code concurrents. Les quotas sont vérifiés AVANT toute écriture disque ou base.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from pathlib import Path

from loguru import logger

from backend.chat import exiger_conversation
from backend.core import maintenant
from backend.fichiers import depot, politique, stockage
from backend.fichiers.erreurs import FichierIntrouvable
from backend.fichiers.modeles import FichierConversation, OrigineFichier


def deposer_fichier(
    conversation_id: str,
    *,
    nom_fourni: str,
    type_mime_declare: str | None,
    octets: bytes,
    origine: OrigineFichier,
    message_id: str | None = None,
) -> FichierConversation:
    """Valide, écrit sur le disque puis enregistre la référence.

    Ordre imposé : la conversation doit exister, le type MIME doit être dans la liste blanche, les
    deux quotas doivent être respectés — TOUT cela avant la première écriture. Un échec à n'importe
    laquelle de ces étapes ne laisse aucune trace, ni sur le disque ni en base.
    """
    exiger_conversation(conversation_id)
    type_mime = politique.valider_type_mime(type_mime_declare)
    politique.verifier_taille_fichier(len(octets))
    politique.verifier_quota_cumule(depot.taille_cumulee(conversation_id), len(octets))

    fichier = _ecrire_et_construire(conversation_id, nom_fourni, type_mime, octets, origine, message_id)
    depot.enregistrer_fichier(fichier)
    logger.debug("Fichier déposé : {} ({} octets, origine={})", fichier.id, fichier.taille_octets, fichier.origine)
    return fichier


def _ecrire_et_construire(
    conversation_id: str,
    nom_fourni: str,
    type_mime: str,
    octets: bytes,
    origine: OrigineFichier,
    message_id: str | None,
) -> FichierConversation:
    """Écrit les octets sur le disque et construit la référence. Appelé une seule fois les
    validations passées : rien ici ne doit pouvoir échouer sur un motif métier."""
    fichier_id = str(uuid.uuid4())
    extension = politique.extension_pour(type_mime)
    chemin_relatif = stockage.ecrire_fichier(conversation_id, fichier_id, extension, octets)
    return FichierConversation(
        id=fichier_id,
        conversation_id=conversation_id,
        message_id=message_id,
        origine=origine,
        nom_affiche=nom_fourni,
        chemin_relatif=chemin_relatif,
        type_mime=type_mime,
        taille_octets=len(octets),
        empreinte_sha256=hashlib.sha256(octets).hexdigest(),
        cree_le=maintenant(),
    )


def lire_fichier(fichier_id: str) -> FichierConversation:
    """Référence enregistrée, ou lève `FichierIntrouvable`."""
    fichier = depot.lire_fichier(fichier_id)
    if fichier is None:
        raise FichierIntrouvable(f"Fichier inconnu : {fichier_id}")
    return fichier


def resoudre_reference(conversation_id: str, reference: str) -> FichierConversation:
    """Fichier de CETTE conversation désigné par son identifiant ou par son nom affiché.

    Un modèle désigne spontanément un fichier par son nom — « hello.py » —, jamais par l'UUID que
    le harnais lui a rendu. Mesuré le 2026-08-16 : `presenter_fichier(fichier_id="hello.py")`
    répondait « aucun fichier n'existe » alors que le fichier venait d'être déposé sous
    l'identifiant `afaaa20c…`. Le refus était exact et inutile ; le modèle a conclu que son
    fichier avait disparu et a tenté de le recréer.

    L'identifiant est essayé d'abord : c'est la désignation sans ambiguïté. Le nom ne sert qu'en
    repli, et à noms égaux le plus récent gagne — c'est celui que le modèle vient de produire.
    Le filtrage par conversation est appliqué dans les DEUX cas : un identifiant d'une autre
    conversation reste introuvable, exactement comme avant.
    """
    reference = reference.strip()
    if not reference:
        raise FichierIntrouvable("Aucune référence de fichier fournie.")

    direct = depot.lire_fichier(reference)
    if direct is not None and direct.conversation_id == conversation_id:
        return direct

    candidats = [f for f in depot.lister_fichiers(conversation_id) if f.nom_affiche == reference]
    if not candidats:
        raise FichierIntrouvable(f"Fichier inconnu dans cette conversation : {reference}")
    return max(candidats, key=lambda fichier: fichier.cree_le)


def chemin_disque(fichier: FichierConversation) -> Path:
    """Chemin absolu résolu et borné au magasin — c'est ce que la route de service ouvre."""
    return stockage.chemin_absolu(fichier.chemin_relatif)


def lier_fichiers_au_message(conversation_id: str, fichier_ids: Sequence[str], message_id: str) -> None:
    """Rattache les pièces déjà déposées (`origine='utilisateur'`) au message qui vient de les envoyer.

    Chaque identifiant est vérifié appartenir à CETTE conversation avant toute écriture : sans ce
    contrôle, un identifiant forgé lierait au message d'un utilisateur le fichier d'une autre
    conversation. Un identifiant inconnu ou étranger est ignoré, journalisé — jamais fatal à l'envoi
    du message, dont le texte reste la partie essentielle.
    """
    for fichier_id in fichier_ids:
        fichier = depot.lire_fichier(fichier_id)
        if fichier is None or fichier.conversation_id != conversation_id:
            logger.warning(
                "Pièce jointe ignorée pour le message {} : {} n'appartient pas à {}.",
                message_id, fichier_id, conversation_id,
            )
            continue
        depot.lier_message(fichier_id, message_id)


def pieces_pour_messages(message_ids: Sequence[str]) -> dict[str, list[FichierConversation]]:
    """Pièces jointes de ces messages, groupées par `message_id` — une requête, pas une par message."""
    return depot.lister_par_messages(message_ids)
