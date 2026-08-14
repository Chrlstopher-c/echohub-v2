"""Orchestration d'un tour de génération : contexte, streaming, annulation, persistance.

Le tour est coupé en deux temps volontairement distincts :

- `preparer()` est synchrone et échoue tôt — conversation inconnue, génération déjà en cours. Tant
  que le flux n'a pas commencé, une erreur peut encore devenir un vrai statut HTTP.
- `diffuser()` est l'itérateur asynchrone. Une fois les en-têtes partis, plus aucun statut n'est
  négociable : tout échec y devient un événement `erreur` dans le flux.

Ce que ce module ne fait pas, et ne fera pas : estimer un nombre de tokens. Si le moteur ne
rapporte pas ses compteurs, ils restent nuls en base. La v1 les fabriquait (`len // 4`), ce qui
donnait des statistiques crédibles et fausses.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from loguru import logger

from backend.chat import annulation, depot, port_inference
from backend.chat.annulation import GenerationActive
from backend.chat.erreurs import BrancheInvalide
from backend.chat.modeles import (
    MAX_TOKENS_PLAFOND,
    DemandeEdition,
    DemandeGeneration,
    DemandeRejeu,
    EvenementDebut,
    EvenementErreur,
    EvenementFin,
    EvenementFlux,
    EvenementFragment,
    MessageChat,
    ParametresEchantillonnage,
    ReglagesConversation,
)
from backend.chat.port_inference import (
    FragmentTexte,
    MessageInference,
    RequeteGeneration,
    StatistiquesGeneration,
)
from backend.core import EchoHubError, MoteurIndisponible

# Un moteur qui n'émet plus rien pendant ce délai est considéré mort. Ce n'est pas un paramètre de
# performance : le préremplissage d'un long prompt avec offload CPU peut légitimement prendre des
# dizaines de secondes, la valeur laisse cette marge tout en bornant l'attente.
DELAI_INACTIVITE_S = 180.0

# Certains moteurs émettent un fragment par morceau de token (caractère UTF-8 multi-octets, espace
# de tête). Cette marge borne la boucle de diffusion sans couper une génération légitime.
MARGE_FRAGMENTS_PAR_TOKEN = 4


@dataclass(slots=True)
class PreparationGeneration:
    """Tout ce que `diffuser()` doit savoir, figé avant l'ouverture du flux.

    `parent_id` est décidé ICI, une fois, et transporté jusqu'à la persistance : relire la feuille
    active au moment d'écrire la réponse rattacherait le message à ce que la conversation est
    devenue entre-temps, pas à ce sur quoi la génération a réellement travaillé.
    """

    conversation_id: str
    message_id: str
    modele_id: str | None
    requete: RequeteGeneration
    generation: GenerationActive
    parent_id: str | None = None
    message_utilisateur_id: str | None = None


@dataclass(slots=True)
class _EtatFlux:
    """État mutable d'un flux en cours, rempli au fil des fragments."""

    debut: float = field(default_factory=time.perf_counter)
    texte: str = ""
    fragments: int = 0
    tokens_generes: int | None = None
    tokens_par_seconde: float | None = None
    interrompu: bool = False

    def duree_ms(self) -> int:
        return max(0, round((time.perf_counter() - self.debut) * 1000))


def preparer(conversation_id: str, demande: DemandeGeneration) -> PreparationGeneration:
    """Valide, persiste le message utilisateur et réserve la conversation. Peut lever.

    Le message s'accroche à la feuille active : on prolonge la branche que l'utilisateur a sous les
    yeux, jamais celle qu'il a quittée.
    """
    conversation = depot.exiger_conversation(conversation_id)
    reglages = depot.lire_reglages(conversation_id)
    modele_id = demande.modele_id or conversation.modele_id
    message_assistant = _identifiant_provisoire()
    generation = annulation.reserver(conversation_id, message_assistant)
    try:
        message_utilisateur = depot.ajouter_message(
            conversation_id,
            role="user",
            contenu=demande.contenu,
            parent_id=depot.feuille_active(conversation_id),
        )
        if modele_id is not None and modele_id != conversation.modele_id:
            depot.definir_modele_conversation(conversation_id, modele_id)
        messages = _construire_contexte(conversation_id, reglages, message_utilisateur.id)
    except EchoHubError:
        annulation.liberer(generation)
        raise

    return _preparation(
        conversation_id=conversation_id,
        message_assistant=message_assistant,
        modele_id=modele_id,
        parametres=demande.parametres or reglages.parametres,
        messages=messages,
        generation=generation,
        ancre=message_utilisateur.id,
        message_utilisateur_id=message_utilisateur.id,
    )


def preparer_rejeu(conversation_id: str, message_id: str, demande: DemandeRejeu) -> PreparationGeneration:
    """Rejoue un message dans une nouvelle sous-branche : l'existante n'est ni modifiée ni perdue."""
    return _preparer_branche(conversation_id, message_id, demande, contenu=None)


def preparer_edition(conversation_id: str, message_id: str, demande: DemandeEdition) -> PreparationGeneration:
    """Édite un message utilisateur : son texte corrigé devient une branche sœur, l'original reste."""
    return _preparer_branche(conversation_id, message_id, demande, contenu=demande.contenu)


def _preparer_branche(
    conversation_id: str,
    message_id: str,
    demande: DemandeRejeu,
    contenu: str | None,
) -> PreparationGeneration:
    """Ouvre une branche sœur du message visé, puis prépare la génération qui l'y prolonge."""
    conversation = depot.exiger_conversation(conversation_id)
    cible = depot.exiger_message(conversation_id, message_id)
    _verifier_branchable(cible, contenu)
    reglages = depot.lire_reglages(conversation_id)
    modele_id = demande.modele_id or conversation.modele_id
    message_assistant = _identifiant_provisoire()
    generation = annulation.reserver(conversation_id, message_assistant)
    try:
        ancre, message_utilisateur_id = _ancrer_branche(cible, contenu)
        messages = _construire_contexte(conversation_id, reglages, ancre)
        # Écrit APRÈS la construction du contexte : une branche refusée ne doit pas déplacer la
        # vue vers un point de l'arbre où rien ne sera généré. Tant que la nouvelle réponse n'est
        # pas persistée, la vue résolue redescend sur la variante existante (cf. `resoudre_feuille`).
        depot.definir_feuille_active(conversation_id, ancre)
    except EchoHubError:
        annulation.liberer(generation)
        raise
    return _preparation(
        conversation_id=conversation_id,
        message_assistant=message_assistant,
        modele_id=modele_id,
        parametres=demande.parametres or reglages.parametres,
        messages=messages,
        generation=generation,
        ancre=ancre,
        message_utilisateur_id=message_utilisateur_id,
    )


def _verifier_branchable(cible: MessageChat, contenu: str | None) -> None:
    """Refuse les branchements qui n'ont pas de sens, avec la raison exacte.

    Réécrire une réponse du modèle en ferait un faux enregistrement de ce qu'il a produit : seule
    la parole de l'utilisateur s'édite. Un message `system` n'est pas un tour de conversation mais
    un réglage — il ne se rejoue pas.
    """
    if cible.role not in ("user", "assistant"):
        raise BrancheInvalide(f"Un message de rôle « {cible.role} » ne porte pas de branche.")
    if contenu is not None and cible.role != "user":
        raise BrancheInvalide("Seul un message utilisateur peut être édité.")


def _ancrer_branche(cible: MessageChat, contenu: str | None) -> tuple[str | None, str | None]:
    """Point d'accroche de la réponse à venir, et message utilisateur créé s'il y en a un.

    Une réponse se rejoue depuis SON parent : la nouvelle réponse devient sa sœur, sans qu'aucun
    message ne soit récrit. Un message utilisateur (rejeu à l'identique ou édition) est recopié en
    sœur : la branche s'ouvre à partir du même parent, et l'original garde sa propre suite.
    """
    if cible.role == "assistant":
        return cible.parent_id, None
    nouveau = depot.ajouter_message(
        cible.conversation_id,
        role="user",
        contenu=cible.contenu if contenu is None else contenu,
        parent_id=cible.parent_id,
    )
    return nouveau.id, nouveau.id


def _preparation(
    *,
    conversation_id: str,
    message_assistant: str,
    modele_id: str | None,
    parametres: ParametresEchantillonnage,
    messages: list[MessageInference],
    generation: GenerationActive,
    ancre: str | None,
    message_utilisateur_id: str | None,
) -> PreparationGeneration:
    """Assemble la préparation. Un seul endroit construit la requête envoyée au moteur."""
    requete = RequeteGeneration(messages=messages, parametres=parametres, modele_id=modele_id)
    return PreparationGeneration(
        conversation_id=conversation_id,
        message_id=message_assistant,
        modele_id=modele_id,
        requete=requete,
        generation=generation,
        parent_id=ancre,
        message_utilisateur_id=message_utilisateur_id,
    )


def _identifiant_provisoire() -> str:
    """Identifiant annoncé au client dès l'ouverture du flux, avant que le message n'existe en base."""
    return str(uuid.uuid4())


def _construire_contexte(
    conversation_id: str,
    reglages: ReglagesConversation,
    ancre: str | None,
) -> list[MessageInference]:
    """Assemble prompt système + chemin jusqu'à l'ancre, en messages, jamais en tokens estimés.

    L'historique est le CHEMIN de la branche visée, pas tous les messages de la conversation : une
    variante abandonnée ne doit plus peser sur ce que le modèle lit.
    """
    historique = _historique_branche(conversation_id, reglages, ancre)
    messages: list[MessageInference] = []
    if reglages.prompt_systeme.strip():
        messages.append(MessageInference(role="system", contenu=reglages.prompt_systeme))
    # Un message vide fait échouer la tokenisation de plusieurs gabarits de chat ; un message
    # `system` en historique doublonnerait le prompt système, qui est un réglage et non un tour.
    messages.extend(
        MessageInference(role=message.role, contenu=message.contenu)
        for message in historique
        if message.role != "system" and message.contenu.strip()
    )
    if not messages:
        # Le port exige au moins un message : une erreur métier lisible vaut mieux qu'une
        # ValidationError remontée en 500 depuis la couche HTTP.
        raise BrancheInvalide("Aucun contenu exploitable en amont de ce point.")
    return messages


def _historique_branche(
    conversation_id: str,
    reglages: ReglagesConversation,
    ancre: str | None,
) -> list[MessageChat]:
    """Chemin racine → ancre, tronqué en NOMBRE DE MESSAGES quand l'utilisateur l'a demandé."""
    historique = [] if ancre is None else depot.chemin_jusqua(conversation_id, ancre)
    if not historique:
        raise BrancheInvalide(
            "Aucun historique en amont de ce point : il n'y a rien à envoyer au moteur.",
            details={"conversation_id": conversation_id, "ancre": ancre},
        )
    if reglages.historique_max_messages is None:
        return historique
    return historique[-reglages.historique_max_messages :]


async def diffuser(preparation: PreparationGeneration) -> AsyncIterator[EvenementFlux]:
    """Streame la réponse, puis persiste ce qui a été produit — y compris après une interruption."""
    annulation.marquer_demarree(preparation.generation)
    etat = _EtatFlux()
    erreur: EvenementErreur | None = None

    yield EvenementDebut(
        conversation_id=preparation.conversation_id,
        message_id=preparation.message_id,
        modele_id=preparation.modele_id,
        parent_id=preparation.parent_id,
        message_utilisateur_id=preparation.message_utilisateur_id,
    )
    try:
        async for texte in _fragments(preparation, etat):
            yield EvenementFragment(texte=texte)
    except GeneratorExit:
        _cloturer_sans_client(preparation, etat)
        raise
    except EchoHubError as exc:
        logger.error("Génération interrompue sur {} : {}", preparation.conversation_id, exc)
        erreur = EvenementErreur(code=exc.code, message=exc.message, remediation=exc.remediation)
    except Exception as exc:  # dernier filet : un moteur tiers peut lever n'importe quoi
        logger.exception("Échec inattendu de la génération sur {}", preparation.conversation_id)
        erreur = EvenementErreur(code="erreur_interne", message=str(exc))
    finally:
        annulation.liberer(preparation.generation)

    erreur = _persister(preparation, etat) or erreur
    if erreur is not None:
        yield erreur
    yield _evenement_fin(preparation, etat)


def _evenement_fin(preparation: PreparationGeneration, etat: _EtatFlux) -> EvenementFin:
    """Dernier événement : ce qui a été mesuré, jamais ce qui aurait pu être estimé."""
    return EvenementFin(
        message_id=preparation.message_id,
        tokens_generes=etat.tokens_generes,
        tokens_par_seconde=etat.tokens_par_seconde,
        duree_ms=etat.duree_ms(),
        interrompu=etat.interrompu,
    )


def _cloturer_sans_client(preparation: PreparationGeneration, etat: _EtatFlux) -> None:
    """Le client s'est déconnecté : plus rien ne peut être émis, mais le texte produit est conservé."""
    etat.interrompu = True
    annulation.liberer(preparation.generation)
    echec = _persister(preparation, etat)
    if echec is not None:
        logger.error("Réponse partielle perdue après déconnexion : {}", echec.message)


async def _fragments(preparation: PreparationGeneration, etat: _EtatFlux) -> AsyncIterator[str]:
    """Boucle de lecture du moteur : bornée en itérations et en inactivité, annulable à chaque tour."""
    moteur = port_inference.obtenir_moteur()
    # `max_tokens` à `None` signifie « pas de plafond demandé » : la boucle reste bornée par le
    # plafond du domaine, qui borne aussi la valeur maximale acceptée en réglage. La borne réelle
    # de la génération est alors la fenêtre de contexte du moteur, plus le délai d'inactivité.
    plafond_tokens = preparation.requete.parametres.max_tokens or MAX_TOKENS_PLAFOND
    plafond = plafond_tokens * MARGE_FRAGMENTS_PAR_TOKEN
    iterateur = moteur.generer(preparation.requete).__aiter__()
    try:
        while etat.fragments < plafond:
            if preparation.generation.arret.is_set():
                etat.interrompu = True
                logger.info("Génération annulée sur {}", preparation.conversation_id)
                break
            element = await _element_suivant(iterateur, preparation.conversation_id)
            if element is None:
                break
            etat.fragments += 1
            texte = _appliquer(element, etat)
            if texte:
                etat.texte += texte
                yield texte
        else:
            # `else` d'un `while` : atteint uniquement quand la condition devient fausse, donc
            # quand le plafond est saturé — les sorties par `break` (fin de flux, annulation) le
            # sautent. C'est ce qui distingue une génération coupée d'une génération terminée.
            etat.interrompu = True
            logger.warning("Plafond de {} fragments atteint sur {}", plafond, preparation.conversation_id)
    finally:
        await _fermer(iterateur)


async def _element_suivant(iterateur: AsyncIterator[object], conversation_id: str) -> object | None:
    """Élément suivant, ou `None` en fin de flux. Une inactivité prolongée devient une erreur claire."""
    try:
        return await asyncio.wait_for(iterateur.__anext__(), timeout=DELAI_INACTIVITE_S)
    except StopAsyncIteration:
        return None
    except asyncio.TimeoutError as exc:
        logger.error("Moteur silencieux depuis {} s sur {}", DELAI_INACTIVITE_S, conversation_id)
        raise MoteurIndisponible(
            f"Le moteur n'a rien émis depuis {DELAI_INACTIVITE_S:.0f} s.",
            remediation="Vérifier l'état du moteur dans l'écran Système, puis recharger le modèle.",
        ) from exc


def _appliquer(element: object, etat: _EtatFlux) -> str:
    """Range l'élément : du texte à émettre, ou des statistiques mesurées à retenir."""
    if isinstance(element, StatistiquesGeneration):
        etat.tokens_generes = element.tokens_generes
        etat.tokens_par_seconde = element.tokens_par_seconde
        return ""
    if isinstance(element, FragmentTexte):
        return element.texte
    logger.debug("Élément de flux ignoré : {}", type(element).__name__)
    return ""


async def _fermer(iterateur: AsyncIterator[object]) -> None:
    """Ferme le flux du moteur — c'est ce qui arrête réellement la génération côté moteur."""
    fermeture = getattr(iterateur, "aclose", None)
    if fermeture is None:
        return
    try:
        await fermeture()
    except Exception as exc:  # une fermeture ratée ne doit pas masquer la cause d'origine
        logger.warning("Fermeture du flux du moteur échouée : {}", exc)


def _persister(preparation: PreparationGeneration, etat: _EtatFlux) -> EvenementErreur | None:
    """Écrit la réponse produite. Un texte partiel est conservé : il a une valeur pour l'utilisateur."""
    if not etat.texte:
        return None
    try:
        depot.ajouter_message(
            preparation.conversation_id,
            role="assistant",
            contenu=etat.texte,
            identifiant=preparation.message_id,
            modele_id=preparation.modele_id,
            tokens_generes=etat.tokens_generes,
            tokens_par_seconde=etat.tokens_par_seconde,
            interrompu=etat.interrompu,
            parent_id=preparation.parent_id,
        )
    except EchoHubError as exc:
        logger.error("Réponse non persistée sur {} : {}", preparation.conversation_id, exc)
        return EvenementErreur(code=exc.code, message=exc.message, remediation=exc.remediation)
    return None
