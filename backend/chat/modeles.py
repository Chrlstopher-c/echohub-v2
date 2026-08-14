"""Structures du domaine `chat` — conversations, messages, réglages, événements de flux.

Un seul endroit décrit la forme des données du domaine : la persistance (`depot`), la génération
(`generation`) et les routes HTTP (`routes`) valident toutes contre ces modèles. C'est ce qui évite
la divergence mesurée sur la v1, où le frontend, le routeur et le service portaient chacun leur
propre idée de ce qu'était une conversation.

Les valeurs par défaut d'échantillonnage reprennent celles de llama.cpp : l'utilisateur qui ne
touche à rien obtient le comportement natif du moteur, pas un réglage inventé ici.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RoleMessage = Literal["system", "user", "assistant"]

# Plafond de `max_tokens`. Il ne décrit aucun matériel : il borne la boucle de diffusion, qui
# dimensionne son nombre maximal d'itérations à partir de cette valeur.
MAX_TOKENS_PLAFOND = 262_144


class ParametresEchantillonnage(BaseModel):
    """Paramètres de génération d'une conversation. Bornes issues des plages admises par llama.cpp."""

    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    top_k: int = Field(default=40, ge=0)
    penalite_repetition: float = Field(default=1.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=MAX_TOKENS_PLAFOND)
    sequences_arret: list[str] = Field(default_factory=list)
    graine: int | None = Field(default=None)


class ReglagesConversation(BaseModel):
    """Prompt système et paramètres attachés à une conversation.

    `historique_max_messages` compte des MESSAGES, jamais des tokens : le domaine `chat` ne connaît
    ni le tokenizer ni la fenêtre de contexte du modèle chargé. La v1 tronquait sur une estimation
    « 4 caractères = 1 token » — exactement le type de constante que la v2 bannit. À `None`,
    l'historique complet part au moteur, qui seul sait ce qu'il peut ingérer.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_systeme: str = ""
    parametres: ParametresEchantillonnage = Field(default_factory=ParametresEchantillonnage)
    historique_max_messages: int | None = Field(default=None, ge=1)


class MessageChat(BaseModel):
    """Message persisté, enrichi des métadonnées propres au domaine chat.

    `tokens_generes` et `tokens_par_seconde` restent à `None` quand le moteur ne les rapporte pas :
    aucune estimation n'est fabriquée pour combler le trou.
    """

    id: str
    conversation_id: str
    role: RoleMessage
    contenu: str
    tokens_generes: int | None = None
    tokens_par_seconde: float | None = None
    cree_le: datetime
    modele_id: str | None = None
    interrompu: bool = False


class ResumeConversation(BaseModel):
    """Ligne de liste : tout sauf les messages."""

    id: str
    titre: str
    modele_id: str | None = None
    cree_le: datetime
    maj_le: datetime
    archivee: bool = False
    nb_messages: int = Field(default=0, ge=0)


class ConversationDetaillee(BaseModel):
    """Conversation complète servie à l'ouverture d'un écran de chat."""

    conversation: ResumeConversation
    reglages: ReglagesConversation
    messages: list[MessageChat]


class CreationConversation(BaseModel):
    """Corps de création. Les réglages omis prennent les valeurs par défaut du domaine."""

    model_config = ConfigDict(extra="forbid")

    titre: str = Field(default="Nouvelle conversation", min_length=1, max_length=200)
    modele_id: str | None = None
    reglages: ReglagesConversation = Field(default_factory=ReglagesConversation)


class MajConversation(BaseModel):
    """Patch partiel : seuls les champs explicitement fournis sont écrits."""

    model_config = ConfigDict(extra="forbid")

    titre: str | None = Field(default=None, min_length=1, max_length=200)
    modele_id: str | None = None
    archivee: bool | None = None


class MajReglages(BaseModel):
    """Patch partiel des réglages. Fusionné avec l'existant, jamais substitué en bloc."""

    model_config = ConfigDict(extra="forbid")

    prompt_systeme: str | None = None
    parametres: ParametresEchantillonnage | None = None
    historique_max_messages: int | None = Field(default=None, ge=1)


class DemandeGeneration(BaseModel):
    """Tour de génération. `parametres` et `modele_id` surchargent les réglages sans les écraser."""

    model_config = ConfigDict(extra="forbid")

    contenu: str = Field(min_length=1)
    modele_id: str | None = None
    parametres: ParametresEchantillonnage | None = None


class EvenementDebut(BaseModel):
    """Premier événement du flux : donne au client l'identifiant du message assistant à venir."""

    type: Literal["debut"] = "debut"
    conversation_id: str
    message_id: str
    modele_id: str | None = None


class EvenementFragment(BaseModel):
    """Morceau de texte généré."""

    type: Literal["fragment"] = "fragment"
    texte: str


class EvenementFin(BaseModel):
    """Dernier événement : statistiques mesurées et cause de l'arrêt."""

    type: Literal["fin"] = "fin"
    message_id: str
    tokens_generes: int | None = None
    tokens_par_seconde: float | None = None
    duree_ms: int = Field(ge=0)
    interrompu: bool = False


class EvenementErreur(BaseModel):
    """Erreur survenue après l'ouverture du flux — le statut HTTP est déjà parti, pas lui."""

    type: Literal["erreur"] = "erreur"
    code: str
    message: str
    remediation: str = ""


EvenementFlux = EvenementDebut | EvenementFragment | EvenementFin | EvenementErreur


def fusionner_reglages(actuels: ReglagesConversation, patch: MajReglages) -> ReglagesConversation:
    """Applique un patch partiel et revalide l'ensemble.

    Passer par `model_validate` plutôt que `model_copy` garantit que les bornes des paramètres sont
    revérifiées : un patch ne doit pas pouvoir installer une valeur qu'une création aurait refusée.
    """
    modifications = patch.model_dump(exclude_unset=True, exclude_none=True)
    return ReglagesConversation.model_validate({**actuels.model_dump(), **modifications})
