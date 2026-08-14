"""Installation d'une version de vLLM dans un venv isolé — annulable et ré-entrante.

Trois exigences dictent la forme de ce module :

**1. Isolation.** vLLM tire torch et une chaîne CUDA (13.0 sur la version mesurée) incompatibles
avec les dépendances du backend. Chaque version vit donc dans son propre venv, jamais dans celui
de l'application.

**2. Ré-entrance.** Une installation interrompue ne doit pas laisser un venv à moitié construit
qui se fait passer pour valide. C'est le défaut exact de la v1. Deux mécanismes se complètent : le
marqueur écrit en deux temps (cf. `venvs.py`), qui survit même à un `SIGKILL`, et le nettoyage
systématique du dossier en sortie d'échec ou d'annulation. Relancer l'installation d'une version
en échec repart toujours d'un dossier vide.

**3. Annulation effective.** L'annulation coupe le sous-processus en cours — un `pip install`
qu'on cesse simplement d'écouter continuerait de peupler le venv pendant vingt minutes.

Contrainte mesurée, appliquée ici : `transformers` doit être en 5.x, sinon les modèles récents
échouent au démarrage sur un tokenizer `TokenizersBackend` inconnu. `xgrammar`, tiré par vLLM,
DÉCLARE pourtant exiger `transformers<5`. Cette borne est trop stricte : l'import fonctionne en
v5 (COMPATIBILITE-GPU.md). On force donc transformers en 5.x après vLLM — pip signalera un
conflit de dépendances, c'est attendu et sans conséquence — puis la sonde de validation VÉRIFIE
que `xgrammar` s'importe. Ignorer la borne n'est pas un acte de foi : c'est un constat refait à
chaque installation, dont l'échec invalide l'installation.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from pathlib import Path

from loguru import logger

from backend.core import InstallationMoteurEchouee
from backend.engines._processus import (
    FluxProcessus,
    ProcessusAnnule,
    ProcessusExpire,
    environnement_process,
)
from backend.engines._sonde import interroger
from backend.engines.modeles import (
    DiagnosticVllm,
    EtapeInstallation,
    EvenementInstallation,
    MarqueurInstallation,
    NiveauEvenement,
    maintenant_utc,
    progression_de,
)
from backend.engines.vllm import venvs

# Contrainte mesurée, pas prudentielle : la 5.x est la seule branche où les modèles récents
# démarrent. La borne haute exclut une v6 dont rien n'est connu à ce jour.
SPECIFICATION_TRANSFORMERS = "transformers>=5,<6"

# Échéances. Toutes sont hautes : elles ne cadencent rien, elles garantissent seulement qu'aucune
# attente n'est infinie. L'installation télécharge plusieurs gigaoctets (vLLM, torch, CUDA).
TIMEOUT_VENV_S = 300.0
TIMEOUT_PIP_S = 600.0
TIMEOUT_INSTALLATION_S = 5_400.0
TIMEOUT_TRANSFORMERS_S = 1_800.0

# `--progress-bar off` : les barres de progression de pip sont faites de retours chariot, qui
# produisent des milliers de lignes inexploitables dans un flux d'événements.
_OPTIONS_PIP: tuple[str, ...] = ("--progress-bar", "off", "--no-input")


class Superviseur:
    """Registre des installations en cours. État partagé explicite, unique et confiné ici.

    Sert à deux choses : refuser deux installations simultanées de la même version, et permettre à
    une autre requête d'annuler celle qui est en cours.
    """

    def __init__(self) -> None:
        self._annulations: dict[str, asyncio.Event] = {}

    def enregistrer(self, version: str) -> asyncio.Event:
        if version in self._annulations:
            raise InstallationMoteurEchouee(
                f"Une installation de vLLM {version} est déjà en cours.",
                remediation="Attendre sa fin ou l'annuler avant d'en relancer une.",
            )
        evenement = asyncio.Event()
        self._annulations[version] = evenement
        return evenement

    def oublier(self, version: str) -> None:
        self._annulations.pop(version, None)

    def annuler(self, version: str) -> bool:
        """Demande l'annulation. Faux si aucune installation ne tourne pour cette version."""
        evenement = self._annulations.get(version)
        if evenement is None:
            return False
        evenement.set()
        logger.info("Annulation demandée pour l'installation de vLLM {}", version)
        return True

    def en_cours(self) -> tuple[str, ...]:
        return tuple(self._annulations)


SUPERVISEUR = Superviseur()

# Une étape est un générateur asynchrone d'événements ; l'orchestrateur les enchaîne.
Etape = Callable[[], AsyncIterator[EvenementInstallation]]


class _Installation:
    """Déroulé d'une installation. Instancié pour une seule exécution, jamais réutilisé."""

    def __init__(self, version: str, *, remplacer: bool) -> None:
        self.version = venvs.valider_version(version)
        self.dossier = venvs.chemin_version(self.version)
        self.remplacer = remplacer
        self.debute_le = maintenant_utc()
        self.annulation: asyncio.Event | None = None
        self.diagnostic: DiagnosticVllm | None = None
        self.reussi = False
        # Flux du sous-processus en cours. Conservé pour pouvoir le tuer depuis le nettoyage, sans
        # dépendre de la finalisation — différée — des générateurs asynchrones imbriqués.
        self._flux_courant: FluxProcessus | None = None

    # -- Fabrication des événements --------------------------------------------------------

    def _evenement(
        self,
        etape: EtapeInstallation,
        message: str,
        *,
        niveau: NiveauEvenement = "info",
        termine: bool = False,
        succes: bool | None = None,
    ) -> EvenementInstallation:
        return EvenementInstallation(
            version=self.version,
            etape=etape,
            message=message,
            niveau=niveau,
            progression=progression_de(etape),
            termine=termine,
            succes=succes,
        )

    def _commande_pip(self, *arguments: str) -> list[str | Path]:
        """Toujours `python -m pip`, jamais le script `bin/pip` : celui-ci fige un chemin absolu."""
        return [venvs.python_de(self.dossier), "-m", "pip", *arguments, *_OPTIONS_PIP]

    async def _diffuser(
        self,
        etape: EtapeInstallation,
        commande: list[str | Path],
        *,
        timeout_s: float,
    ) -> AsyncIterator[EvenementInstallation]:
        """Exécute une commande en relayant sa sortie. Lève si le code retour n'est pas nul."""
        flux = FluxProcessus(
            commande=commande,
            timeout_s=timeout_s,
            annulation=self.annulation,
            environnement=environnement_process(),
        )
        self._flux_courant = flux
        async for ligne in flux.lignes():
            if ligne:
                yield self._evenement(etape, ligne)
        self._flux_courant = None
        if flux.code_retour != 0:
            raise InstallationMoteurEchouee(
                f"Étape « {etape.value} » échouée (code {flux.code_retour}).",
                remediation="Consulter les lignes précédentes du journal d'installation.",
                details={"version": self.version, "etape": etape.value},
            )

    # -- Étapes ----------------------------------------------------------------------------

    async def _preparer(self) -> AsyncIterator[EvenementInstallation]:
        etape = EtapeInstallation.PREPARATION
        yield self._evenement(etape, f"Installation de vLLM {self.version} dans {self.dossier}")
        marqueur = venvs.lire_marqueur(self.dossier)
        if marqueur is not None and marqueur.statut == "valide" and not self.remplacer:
            raise InstallationMoteurEchouee(
                f"vLLM {self.version} est déjà installé et validé.",
                remediation="Supprimer cette version d'abord, ou demander explicitement son remplacement.",
            )
        if self.dossier.exists():
            yield self._evenement(
                etape,
                "Contenu existant supprimé : une installation repart toujours d'un dossier vide.",
                niveau="avertissement",
            )
            venvs.nettoyer_residu(self.dossier)
        self.dossier.parent.mkdir(parents=True, exist_ok=True)

    async def _creer_venv(self) -> AsyncIterator[EvenementInstallation]:
        etape = EtapeInstallation.CREATION_VENV
        yield self._evenement(etape, "Création du venv isolé (torch et CUDA séparés du backend).")
        # `sys.executable` : le venv hérite de l'interpréteur du backend, donc de la version de
        # Python fournie par l'image. Nommer un binaire en dur (« python3.11 », comme la v1)
        # revient à parier sur ce qui est installé dans le conteneur.
        commande: list[str | Path] = [sys.executable, "-m", "venv", self.dossier]
        async for evenement in self._diffuser(etape, commande, timeout_s=TIMEOUT_VENV_S):
            yield evenement
        python = venvs.python_de(self.dossier)
        if not python.exists():
            raise InstallationMoteurEchouee(
                "Le venv a été créé sans interpréteur exploitable.",
                remediation="Vérifier que le paquet python3-venv est présent dans l'image.",
                details={"chemin": str(python)},
            )
        venvs.ecrire_marqueur(self.dossier, self._marqueur("en_cours"))

    async def _mettre_a_jour_pip(self) -> AsyncIterator[EvenementInstallation]:
        etape = EtapeInstallation.MISE_A_JOUR_PIP
        yield self._evenement(etape, "Mise à jour de pip dans le venv.")
        async for evenement in self._diffuser(
            etape, self._commande_pip("install", "--upgrade", "pip"), timeout_s=TIMEOUT_PIP_S
        ):
            yield evenement

    async def _installer_vllm(self) -> AsyncIterator[EvenementInstallation]:
        etape = EtapeInstallation.INSTALLATION_VLLM
        yield self._evenement(
            etape, f"Installation de vllm=={self.version} — plusieurs gigaoctets à télécharger."
        )
        async for evenement in self._diffuser(
            etape, self._commande_pip("install", f"vllm=={self.version}"), timeout_s=TIMEOUT_INSTALLATION_S
        ):
            yield evenement

    async def _aligner_transformers(self) -> AsyncIterator[EvenementInstallation]:
        etape = EtapeInstallation.ALIGNEMENT_TRANSFORMERS
        yield self._evenement(
            etape,
            "Passage de transformers en 5.x : sans lui, les modèles récents échouent au démarrage "
            "sur un tokenizer TokenizersBackend inconnu.",
        )
        yield self._evenement(
            etape,
            "pip va signaler un conflit avec xgrammar, qui déclare transformers<5. Cette borne est "
            "trop stricte ; l'étape de validation vérifie que l'import passe réellement.",
            niveau="avertissement",
        )
        async for evenement in self._diffuser(
            etape,
            self._commande_pip("install", "--upgrade", SPECIFICATION_TRANSFORMERS),
            timeout_s=TIMEOUT_TRANSFORMERS_S,
        ):
            yield evenement

    async def _valider(self) -> AsyncIterator[EvenementInstallation]:
        etape = EtapeInstallation.VALIDATION
        yield self._evenement(etape, "Validation : import réel de vLLM, de transformers et de xgrammar.")
        charge = await interroger(
            venvs.python_de(self.dossier), venvs.SCRIPT_SONDE, timeout_s=venvs.TIMEOUT_SONDE_S
        )
        if charge.donnees is None:
            raise InstallationMoteurEchouee(
                "La sonde de validation n'a produit aucun résultat exploitable.",
                remediation="L'installation est incomplète, ou l'import de vLLM fait tomber le process.",
                details={"sortie": charge.sortie_brute[-1_000:]},
            )
        diagnostic = DiagnosticVllm.model_validate(charge.donnees)
        for evenement in self._verifier(etape, diagnostic):
            yield evenement
        self.diagnostic = diagnostic

    def _verifier(self, etape: EtapeInstallation, diagnostic: DiagnosticVllm) -> list[EvenementInstallation]:
        """Refuse l'installation qui ne satisfait pas les trois conditions mesurées."""
        if not diagnostic.importable:
            raise InstallationMoteurEchouee(
                f"vLLM ne s'importe pas dans le venv fraîchement installé : {diagnostic.erreur}",
                remediation="Vérifier la compatibilité de cette version avec la chaîne CUDA de l'image.",
            )
        majeure = (diagnostic.version_transformers or "0").split(".")[0]
        if not majeure.isdigit() or int(majeure) < 5:
            raise InstallationMoteurEchouee(
                f"transformers est en {diagnostic.version_transformers}, la 5.x est requise.",
                remediation="Une dépendance a redescendu transformers ; relancer l'installation.",
            )
        if diagnostic.xgrammar_importable is False:
            raise InstallationMoteurEchouee(
                "xgrammar ne s'importe plus avec transformers 5.x.",
                remediation="La borne transformers<5 déclarée par xgrammar cesse d'être contournable : "
                "choisir une version de vLLM dont la dépendance xgrammar est compatible.",
            )
        architectures = ", ".join(diagnostic.architectures_gpu) or "aucune"
        return [
            self._evenement(
                etape,
                f"vLLM {diagnostic.version_vllm} · torch {diagnostic.version_torch} · "
                f"CUDA {diagnostic.version_cuda} · transformers {diagnostic.version_transformers}",
                niveau="succes",
            ),
            self._evenement(etape, f"Architectures GPU compilées : {architectures}"),
        ]

    def _finaliser(self) -> EvenementInstallation:
        etape = EtapeInstallation.FINALISATION
        if self.diagnostic is None:
            raise InstallationMoteurEchouee("Finalisation demandée sans diagnostic de validation.")
        venvs.ecrire_marqueur(self.dossier, self._marqueur("valide"))
        self.reussi = True
        logger.info("vLLM {} installé et validé dans {}", self.version, self.dossier)
        return self._evenement(
            etape,
            f"vLLM {self.version} installé et validé.",
            niveau="succes",
            termine=True,
            succes=True,
        )

    def _marqueur(self, statut: str) -> MarqueurInstallation:
        """Marqueur d'état. `valide` n'est écrit qu'après la sonde — c'est toute la garantie."""
        diagnostic = self.diagnostic
        valide = statut == "valide"
        return MarqueurInstallation(
            version_demandee=self.version,
            statut="valide" if valide else "en_cours",
            debute_le=self.debute_le,
            validee_le=maintenant_utc() if valide else None,
            version_vllm=diagnostic.version_vllm if diagnostic else None,
            version_transformers=diagnostic.version_transformers if diagnostic else None,
            version_torch=diagnostic.version_torch if diagnostic else None,
            architectures_gpu=diagnostic.architectures_gpu if diagnostic else (),
            taille_octets=venvs.taille_octets(self.dossier) if valide else None,
        )

    # -- Orchestration ---------------------------------------------------------------------

    async def _derouler(self) -> AsyncIterator[EvenementInstallation]:
        etapes: tuple[Etape, ...] = (
            self._preparer,
            self._creer_venv,
            self._mettre_a_jour_pip,
            self._installer_vllm,
            self._aligner_transformers,
            self._valider,
        )
        for etape in etapes:
            async for evenement in etape():
                yield evenement
        yield self._finaliser()

    async def executer(self) -> AsyncGenerator[EvenementInstallation, None]:
        self.annulation = SUPERVISEUR.enregistrer(self.version)
        try:
            async for evenement in self._derouler():
                yield evenement
        except ProcessusAnnule:
            yield self._evenement(
                EtapeInstallation.ANNULATION,
                "Installation annulée : le venv partiel a été supprimé.",
                niveau="avertissement",
                termine=True,
                succes=False,
            )
        except (InstallationMoteurEchouee, ProcessusExpire, OSError) as exc:
            logger.error("Installation de vLLM {} échouée : {}", self.version, exc)
            yield self._evenement(
                EtapeInstallation.ECHEC,
                f"Installation échouée : {exc}",
                niveau="erreur",
                termine=True,
                succes=False,
            )
        finally:
            # Exécuté aussi quand le consommateur ferme le flux (client déconnecté). Échec,
            # annulation ou abandon laissent toujours le disque dans l'état d'avant.
            SUPERVISEUR.oublier(self.version)
            if not self.reussi:
                self._nettoyer()

    def _nettoyer(self) -> None:
        """Ramène le disque à son état d'avant. Entièrement synchrone : appelé depuis un `finally`."""
        if self.annulation is not None:
            self.annulation.set()
        if self._flux_courant is not None:
            self._flux_courant.tuer()
        try:
            venvs.nettoyer_residu(self.dossier)
        except InstallationMoteurEchouee as exc:
            # Le marqueur reste en « en_cours » : le venv sera signalé INCOMPLET, jamais utilisable.
            logger.error("Nettoyage après échec impossible pour {} : {}", self.dossier, exc)


def installer(version: str, *, remplacer: bool = False) -> AsyncGenerator[EvenementInstallation, None]:
    """Installe une version de vLLM en diffusant sa progression, étape par étape.

    Retourne le générateur du déroulé **sans l'envelopper**, et ce détail est le contrat : fermer
    ce flux (`aclose`, ou une déconnexion client) doit exécuter tout de suite le nettoyage. Une
    fonction enveloppante `async def` interposerait un générateur de plus, dont la fermeture ne
    finaliserait celui du dessous qu'au passage du ramasse-miettes — l'installation continuerait
    alors dans le vide. Constat mesuré pendant l'écriture de ce module, pas une précaution.
    """
    return _Installation(version, remplacer=remplacer).executer()


def annuler(version: str) -> bool:
    """Interrompt une installation en cours. Faux si aucune ne tourne pour cette version."""
    return SUPERVISEUR.annuler(venvs.valider_version(version))


def installations_en_cours() -> tuple[str, ...]:
    """Versions dont une installation est en cours dans ce process."""
    return SUPERVISEUR.en_cours()
