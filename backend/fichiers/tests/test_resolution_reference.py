"""Preuve que `resoudre_reference` accepte le NOM d'un fichier, pas seulement son identifiant.

Défaut réel du 2026-08-16 : le modèle venait de produire `hello.py` via `executer_python`, le
harnais lui rendait « hello.py (id afaaa20c-…) », et l'appel suivant — `presenter_fichier` avec
« hello.py » — se voyait répondre « aucun fichier n'existe ». Le refus était exact au sens strict
et inutile en pratique : le modèle en a conclu que son fichier avait disparu et a tenté de le
recréer, deux tours durant.

Le cloisonnement par conversation reste la propriété non négociable : elle est vérifiée ici sur
les DEUX formes de référence, l'identifiant comme le nom.
"""

from __future__ import annotations

import pytest

from backend.chat.modeles import ResumeConversation
from backend.fichiers import FichierConversation, FichierIntrouvable, deposer_fichier, resoudre_reference


def _deposer(conversation_id: str, nom: str, contenu: bytes = b"print('salut')\n") -> FichierConversation:
    return deposer_fichier(
        conversation_id,
        nom_fourni=nom,
        type_mime_declare="text/plain",
        octets=contenu,
        origine="modele",
    )


def test_resolution_par_identifiant(conversation: ResumeConversation) -> None:
    depose = _deposer(conversation.id, "hello.py")
    assert resoudre_reference(conversation.id, depose.id).id == depose.id


def test_resolution_par_nom_affiche(conversation: ResumeConversation) -> None:
    """Le cas qui manquait : le modèle désigne « hello.py », jamais l'UUID qu'on lui a rendu."""
    depose = _deposer(conversation.id, "hello.py")
    assert resoudre_reference(conversation.id, "hello.py").id == depose.id


def test_le_plus_recent_gagne_a_noms_egaux(conversation: ResumeConversation) -> None:
    """Un fichier réécrit porte le même nom : c'est la dernière version que le modèle veut montrer."""
    _deposer(conversation.id, "hello.py", b"# premiere version\n")
    dernier = _deposer(conversation.id, "hello.py", b"# seconde version\n")
    assert resoudre_reference(conversation.id, "hello.py").id == dernier.id


def test_un_nom_d_une_autre_conversation_reste_introuvable(
    conversation: ResumeConversation, autre_conversation: ResumeConversation
) -> None:
    """Le repli par nom ne doit pas devenir une fuite entre conversations."""
    _deposer(autre_conversation.id, "secret.py")
    with pytest.raises(FichierIntrouvable):
        resoudre_reference(conversation.id, "secret.py")


def test_un_identifiant_d_une_autre_conversation_reste_introuvable(
    conversation: ResumeConversation, autre_conversation: ResumeConversation
) -> None:
    etranger = _deposer(autre_conversation.id, "secret.py")
    with pytest.raises(FichierIntrouvable):
        resoudre_reference(conversation.id, etranger.id)


def test_reference_vide_refusee(conversation: ResumeConversation) -> None:
    with pytest.raises(FichierIntrouvable):
        resoudre_reference(conversation.id, "   ")
