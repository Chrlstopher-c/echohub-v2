"""Preuve qu'un appel d'outil n'est plus jeté pour un synonyme d'argument, et qu'un échec se voit.

Défaut mesuré sur une conversation réelle du 2026-08-16 (message 143 en base). Le modèle a émis
`ecrire_fichier` avec le CONTENU ENTIER du fichier — 12 173 caractères de HTML valide — et un
argument nommé `nom` au lieu de `chemin`. Le harnais a répondu « Échec : Aucun chemin fourni » et
jeté le travail. Le modèle a alors réémis l'appel VIDE, trois tours de suite, puis a annoncé à
l'utilisateur un fichier qui n'existait pas.

Le refus était un choix du harnais, pas une contrainte : il y avait exactement un argument requis
manquant et exactement un argument inconnu, l'intention était lisible. Un alias DÉCLARÉ est une
correspondance explicite et testée — pas un appariement automatique des arguments inattendus, qui
aurait pu déverser un contenu dans un chemin.

Second point prouvé ici : un outil qui échoue le DIT désormais (`EchecOutil`), au lieu de rendre un
texte commençant par « Échec » avec `succes=True`. C'est ce booléen qui permet au harnais de savoir
qu'un tour n'a rien produit, donc de ne pas laisser annoncer un fichier inexistant.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.chat.modeles import ResumeConversation
from backend.outils import registre
from backend.outils.contrat import ContexteExecution, DescriptionOutil, EchecOutil
from backend.outils.fichiers_bac import DESCRIPTION_ECRIRE

CONTENU_REEL = "<!DOCTYPE html>\n<html lang=\"fr\">\n<head><title>Catalogue</title></head>\n</html>\n"


def _contexte(conversation: ResumeConversation, racine_bac: Path) -> ContexteExecution:
    return ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)


def test_un_synonyme_devient_le_nom_canonique() -> None:
    normalises = DESCRIPTION_ECRIRE.normaliser({"nom": "page.html", "contenu": "x"})
    assert normalises == {"chemin": "page.html", "contenu": "x"}


def test_le_nom_canonique_deja_present_gagne_sur_son_alias() -> None:
    """Sinon un alias écraserait une valeur que le modèle a explicitement nommée."""
    normalises = DESCRIPTION_ECRIRE.normaliser({"chemin": "vrai.html", "nom": "autre.html", "contenu": "x"})
    assert normalises["chemin"] == "vrai.html"
    assert "nom" not in normalises


def test_un_argument_inconnu_sans_alias_declare_reste_intact() -> None:
    """La normalisation n'est pas un appariement au jugé : elle n'applique que ce qui est déclaré."""
    normalises = DESCRIPTION_ECRIRE.normaliser({"chemin": "a.html", "contenu": "x", "farfelu": "y"})
    assert normalises["farfelu"] == "y"


def test_les_alias_ne_sont_pas_declares_au_modele() -> None:
    """Le schéma doit rester une consigne unique — sinon on apprend au modèle qu'il a le choix."""
    schema = DESCRIPTION_ECRIRE.vers_format_moteur()
    assert "nom" not in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["chemin", "contenu"]


def test_le_cas_reel_du_transcript_ecrit_maintenant_le_fichier(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    """Le rejeu exact de l'appel qui a coûté 12 173 caractères : `contenu` + `nom`, sans `chemin`."""
    resultat = asyncio.run(
        registre.executer(
            "ecrire_fichier",
            {"contenu": CONTENU_REEL, "nom": "catalogue.html"},
            _contexte(conversation, racine_bac),
        )
    )

    assert resultat.succes, resultat.texte
    assert (racine_bac / "catalogue.html").read_text(encoding="utf-8") == CONTENU_REEL


def test_les_arguments_affiches_restent_ceux_que_le_modele_a_envoyes(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    """L'utilisateur doit voir la demande RÉELLE, pas la version corrigée par le harnais."""
    resultat = asyncio.run(
        registre.executer(
            "ecrire_fichier",
            {"contenu": "x", "nom": "vu.html"},
            _contexte(conversation, racine_bac),
        )
    )

    assert resultat.arguments == {"contenu": "x", "nom": "vu.html"}


def test_un_appel_incomplet_echoue_en_disant_quoi_envoyer(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    """L'échec nomme les arguments attendus ET ce qui a été reçu — l'ancien message ne faisait ni l'un ni l'autre."""
    resultat = asyncio.run(
        registre.executer("ecrire_fichier", {}, _contexte(conversation, racine_bac))
    )

    assert not resultat.succes, "un appel vide n'est pas un succès"
    assert "chemin" in resultat.texte and "contenu" in resultat.texte
    assert "SAME call" in resultat.texte
    assert "nothing" in resultat.texte, "ce que le modèle a envoyé est rappelé"


def test_un_echec_attendu_ne_passe_pas_pour_une_panne(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    """`EchecOutil` part tel quel : sans le préfixe « Échec de l'outil » du filet à `Exception`."""
    resultat = asyncio.run(
        registre.executer("lire_fichier", {"chemin": "absent.txt"}, _contexte(conversation, racine_bac))
    )

    assert not resultat.succes
    assert not resultat.texte.startswith("Échec de l'outil :")
    assert "absent.txt" in resultat.texte


def test_une_ecriture_reussie_reste_un_succes(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    """Garde-fou du booléen : à trop vouloir détecter l'échec, on finirait par ne plus voir le succès."""
    resultat = asyncio.run(
        registre.executer(
            "ecrire_fichier", {"chemin": "ok.txt", "contenu": "bonjour"}, _contexte(conversation, racine_bac)
        )
    )

    assert resultat.succes


def test_echec_outil_est_bien_une_exception() -> None:
    """Elle doit pouvoir être levée depuis n'importe quel outil, sans dépendre de Pydantic."""
    assert issubclass(EchecOutil, Exception)
    assert isinstance(DESCRIPTION_ECRIRE, DescriptionOutil)
