"""Téléchargement des modèles — progression mesurée, reprise, annulation immédiate et sans dégât.

Trois défauts de la v1 sont corrigés ici, et l'ordre des opérations est ce qui les corrige :

1. **L'annulation détruisait le dossier pendant que la bibliothèque écrivait dedans.** Le transfert
   échouait ensuite sur un `FileNotFoundError` incompréhensible, et le dossier avait disparu. Ici
   l'annulation arrête d'abord le processus, attend sa mort, et ne supprime quoi que ce soit
   qu'ensuite — et seulement si on le lui demande.

2. **Rien ne survivait à un redémarrage.** Le transfert se faisait dans un thread, non
   interruptible et non persisté. Ici l'état passe par `download_journal`, et un téléchargement
   trouvé « en cours » au démarrage est marqué `interrompu` : ses octets restent sur le disque et
   une relance reprend où ça s'était arrêté.

3. **Il n'existait aucun moyen d'interrompre un transfert en cours.** `huggingface_hub` n'expose
   pas de jeton d'annulation et un thread Python ne s'interrompt pas. Le transfert tourne donc dans
   un **processus fils** : l'arrêter est immédiat, et les fragments déjà écrits restent
   réutilisables. Le contexte `spawn` est explicite — dupliquer par `fork` un serveur uvicorn qui
   porte des threads, une boucle d'événements et des connexions SQLite ouvertes est une source de
   blocages silencieux.

Ce module ne porte que la machine à états. Ce qu'on va chercher et ce que ça pèse est décidé par
`download_selection` (fonctions pures, vérifiables sans réseau) ; le transfert lui-même et le
nettoyage vivent dans `download_worker`, qui doit rester importable dans un processus `spawn`.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import threading
from collections.abc import AsyncIterator
from functools import lru_cache
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue as FileProcessus
from pathlib import Path
from queue import Empty

from loguru import logger

from backend.core.config import get_settings
from backend.core.db import maintenant
from backend.core.errors import ModeleIntrouvable
from backend.models.discovery import FichierDepot, inventaire
from backend.models.download_journal import (
    ETATS_TERMINAUX,
    EtatTelechargement,
    JournalTelechargements,
    Telechargement,
)
from backend.models.download_selection import (
    motifs_ignores,
    octets_recus,
    octets_totaux,
    parts_du_meme_modele,
    resoudre_cible,
)
from backend.models.download_worker import executer_telechargement, remediation, supprimer
from backend.models.registry import enregistrer
from backend.models.storage import dossier_interne, dossier_modele, identifiant as identifiant_modele

# Sondage de la progression : assez fin pour une barre fluide, assez lâche pour ne pas parcourir le
# disque en boucle sur un transfert de plusieurs dizaines de gigaoctets.
INTERVALLE_SONDAGE_S = 1.0
# Borne dure du suivi d'un transfert. Aucune boucle d'attente ne tourne sans plafond.
MAX_SONDAGES = 24 * 3600
DELAI_ARRET_S = 10.0
DELAI_KILL_S = 5.0
DELAI_VERDICT_S = 5.0

INTERVALLE_DIFFUSION_S = 0.5
MAX_ITERATIONS_DIFFUSION = int(24 * 3600 / INTERVALLE_DIFFUSION_S)


class GestionnaireTelechargements:
    """Cycle de vie des téléchargements : démarrage, suivi, annulation, reprise."""

    def __init__(self, journal: JournalTelechargements) -> None:
        self._verrou = threading.RLock()
        self._journal = journal
        self._etats: dict[str, Telechargement] = journal.charger()
        self._processus: dict[str, BaseProcess] = {}
        self._files: dict[str, FileProcessus[dict[str, str]]] = {}
        self._contexte = multiprocessing.get_context("spawn")

    # --- lecture ------------------------------------------------------------------------------

    def lister(self) -> list[Telechargement]:
        """Tous les téléchargements connus, du plus récent au plus ancien."""
        with self._verrou:
            return sorted(self._etats.values(), key=lambda etat: etat.demarre_le, reverse=True)

    def etat(self, identifiant: str) -> Telechargement:
        """État d'un téléchargement, ou `ModeleIntrouvable` s'il n'a jamais existé."""
        with self._verrou:
            trouve = self._etats.get(identifiant)
        if trouve is None:
            raise ModeleIntrouvable(
                f"Aucun téléchargement connu sous l'identifiant « {identifiant} ».",
                details={"identifiant": identifiant},
            )
        return trouve

    # --- écriture d'état ----------------------------------------------------------------------

    def _enregistrer(self, etat: Telechargement) -> Telechargement:
        """Range un état et le persiste dans la foulée — jamais l'un sans l'autre."""
        with self._verrou:
            etat.maj_le = maintenant()
            self._etats[etat.identifiant] = etat
            self._journal.ecrire(self._etats)
        return etat

    def _muter(self, identifiant: str, **champs: object) -> Telechargement:
        """Applique des changements de champs à un état existant."""
        courant = self.etat(identifiant)
        return self._enregistrer(courant.model_copy(update=champs))

    # --- démarrage ----------------------------------------------------------------------------

    def demarrer(self, depot: str, *, fichier: str | None = None, revision: str = "main") -> Telechargement:
        """Lance ou relance un téléchargement. Idempotent tant qu'un transfert est déjà actif."""
        fichiers = inventaire(depot, revision)
        cible = resoudre_cible(depot, fichier, fichiers)
        motifs = motifs_ignores(fichiers)
        identifiant = identifiant_modele(depot, cible)

        with self._verrou:
            existant = self._etats.get(identifiant)
            if existant is not None and existant.actif and self._vivant(identifiant):
                logger.info("Téléchargement déjà en cours : {}", identifiant)
                return existant

        dossier = dossier_modele(depot)
        etat = self._preparer(identifiant, depot, cible, revision, dossier, fichiers, motifs)
        # Un GGUF découpé n'existe qu'entier : choisir une part revient à demander toutes ses
        # sœurs. Sans cela le transfert s'annonce « terminé » sur un modèle inchargeable.
        parts = parts_du_meme_modele(cible, fichiers) if cible else None
        if parts and len(parts) > 1:
            logger.info("{} est découpé en {} parts : toutes seront récupérées", cible, len(parts))
        self._lancer(etat, motifs, parts)
        return self.etat(identifiant)

    def _preparer(
        self,
        identifiant: str,
        depot: str,
        cible: str | None,
        revision: str,
        dossier: Path,
        fichiers: list[FichierDepot],
        motifs: list[str],
    ) -> Telechargement:
        """Construit l'état initial, en repartant des octets déjà présents s'il y en a."""
        horodatage = maintenant()
        return self._enregistrer(
            Telechargement(
                identifiant=identifiant,
                depot=depot,
                fichier=cible,
                revision=revision,
                chemin=str(dossier),
                etat=EtatTelechargement.EN_ATTENTE,
                octets_recus=octets_recus(dossier, cible),
                octets_totaux=octets_totaux(fichiers, cible, motifs),
                erreur=None,
                remediation=None,
                demarre_le=horodatage,
                maj_le=horodatage,
                termine_le=None,
            )
        )

    def _lancer(self, etat: Telechargement, motifs: list[str], parts: list[str] | None = None) -> None:
        """Démarre le processus fils et le thread qui le surveille."""
        jeton = get_settings().hf_token
        file: FileProcessus[dict[str, str]] = self._contexte.Queue()
        processus = self._contexte.Process(
            target=executer_telechargement,
            args=(
                etat.depot,
                etat.fichier,
                etat.revision,
                etat.chemin,
                jeton.get_secret_value() if jeton else None,
                motifs,
                file,
                parts,
            ),
            name=f"telechargement-{etat.identifiant}",
            daemon=True,
        )
        processus.start()

        with self._verrou:
            self._processus[etat.identifiant] = processus
            self._files[etat.identifiant] = file
        self._muter(etat.identifiant, etat=EtatTelechargement.EN_COURS)

        surveillant = threading.Thread(
            target=self._surveiller, args=(etat.identifiant,), name=f"suivi-{etat.identifiant}", daemon=True
        )
        surveillant.start()
        logger.info("Téléchargement démarré : {} (pid {})", etat.identifiant, processus.pid)

    # --- surveillance -------------------------------------------------------------------------

    def _vivant(self, identifiant: str) -> bool:
        processus = self._processus.get(identifiant)
        return processus is not None and processus.is_alive()

    def _surveiller(self, identifiant: str) -> None:
        """Suit un transfert jusqu'à sa fin, en mesurant la progression sur le disque."""
        with self._verrou:
            processus = self._processus.get(identifiant)
        if processus is None:
            return

        for _ in range(MAX_SONDAGES):
            processus.join(timeout=INTERVALLE_SONDAGE_S)
            if not processus.is_alive():
                break
            self._progresser(identifiant)
        else:
            logger.error("Suivi de {} arrêté sur sa borne de {} sondages", identifiant, MAX_SONDAGES)

        self._finaliser(identifiant)

    def _progresser(self, identifiant: str) -> None:
        """Reporte les octets présents sur le disque dans l'état diffusé."""
        try:
            courant = self.etat(identifiant)
        except ModeleIntrouvable:
            return
        if not courant.actif:
            return
        recus = octets_recus(Path(courant.chemin), courant.fichier)
        if recus != courant.octets_recus:
            self._muter(identifiant, octets_recus=recus)

    def _verdict(self, identifiant: str) -> dict[str, str] | None:
        """Récupère le verdict du processus fils, ou `None` s'il est mort sans en rendre un."""
        with self._verrou:
            file = self._files.pop(identifiant, None)
        if file is None:
            return None
        try:
            return file.get(timeout=DELAI_VERDICT_S)
        except (Empty, OSError, ValueError) as exc:
            # File vide ou fils tué avant d'avoir répondu : c'est un cas normal, pas une panne.
            logger.debug("Aucun verdict du processus {} : {}", identifiant, exc)
            return None

    def _finaliser(self, identifiant: str) -> None:
        """Fixe l'état terminal une fois le processus fils sorti."""
        verdict = self._verdict(identifiant)
        with self._verrou:
            self._processus.pop(identifiant, None)
        courant = self.etat(identifiant)
        if courant.etat is EtatTelechargement.ANNULE:
            return

        recus = octets_recus(Path(courant.chemin), courant.fichier)
        if verdict is None:
            self._conclure_sans_verdict(identifiant, recus)
        elif verdict.get("resultat") == "ok":
            self._conclure_succes(identifiant, recus)
        else:
            self._conclure_echec(identifiant, recus, verdict)

    def _conclure_sans_verdict(self, identifiant: str, recus: int) -> None:
        """Le fils est mort sans rendre de verdict : arrêt du backend, OOM, ou signal externe."""
        logger.warning("Téléchargement {} interrompu sans verdict, {} octets conservés", identifiant, recus)
        self._muter(
            identifiant,
            etat=EtatTelechargement.INTERROMPU,
            octets_recus=recus,
            erreur="Le transfert s'est arrêté sans rendre de verdict.",
            remediation="Relancer : la reprise repart des octets déjà écrits, rien n'est retéléchargé.",
            termine_le=maintenant(),
        )

    def _conclure_succes(self, identifiant: str, recus: int) -> None:
        etat = self._muter(
            identifiant, etat=EtatTelechargement.TERMINE, octets_recus=recus, termine_le=maintenant()
        )
        logger.info("Téléchargement terminé : {} ({} octets)", identifiant, recus)
        try:
            enregistrer(etat.depot, fichier=etat.fichier)
        except Exception as exc:  # noqa: BLE001 — un registre en échec ne défait pas un transfert réussi
            logger.error("Inscription au registre échouée pour {} : {}", identifiant, exc)

    def _conclure_echec(self, identifiant: str, recus: int, verdict: dict[str, str]) -> None:
        message = verdict.get("message", "cause inconnue")
        logger.error("Téléchargement {} en échec : {}", identifiant, message)
        self._muter(
            identifiant,
            etat=EtatTelechargement.ERREUR,
            octets_recus=recus,
            erreur=message,
            remediation=remediation(message),
            termine_le=maintenant(),
        )

    # --- annulation ---------------------------------------------------------------------------

    def oublier(self, identifiant: str, *, supprimer_fichiers: bool = False) -> Telechargement:
        """Retire du journal un transfert déjà terminé, échoué ou annulé.

        Distinct d'`annuler`, qui interrompt un transfert VIVANT. Sans cette opération, une entrée
        terminée restait affichée pour toujours et le bouton de suppression ne produisait rien —
        `annuler` rendait l'état inchangé sans rien faire, ce qui ressemblait exactement à une
        interface morte.

        Les fichiers ne partent que si on le demande : une ligne d'historique et des gigaoctets sur
        le disque ne se suppriment pas d'un même geste sans le dire.
        """
        courant = self.etat(identifiant)
        if courant.etat not in ETATS_TERMINAUX:
            return self.annuler(identifiant, supprimer_fichiers=supprimer_fichiers)
        return self._retirer_entree(courant, supprimer_fichiers)

    def _retirer_entree(self, etat: Telechargement, supprimer_fichiers: bool) -> Telechargement:
        """Efface l'entrée du journal, et les fichiers si on l'a demandé. Sans condition d'état."""
        if supprimer_fichiers:
            supprimer(Path(etat.chemin), etat.fichier)
        with self._verrou:
            self._etats.pop(etat.identifiant, None)
            self._journal.ecrire(self._etats)
        logger.info("Transfert oublié : {} (fichiers supprimés : {})", etat.identifiant, supprimer_fichiers)
        return etat

    def annuler(self, identifiant: str, *, supprimer_fichiers: bool = False) -> Telechargement:
        """Annule un téléchargement. L'ordre des étapes est ce qui rend l'opération sûre."""
        courant = self.etat(identifiant)
        if courant.etat in ETATS_TERMINAUX:
            # Rien à interrompre : la demande porte alors sur l'entrée d'historique elle-même.
            return self._retirer_entree(courant, supprimer_fichiers)

        # 1. l'intention est persistée d'abord : une coupure ici ne laisse pas un état « en cours »
        #    orphelin au redémarrage.
        etat = self._muter(identifiant, etat=EtatTelechargement.ANNULE, termine_le=maintenant())
        with self._verrou:
            processus = self._processus.pop(identifiant, None)
            self._files.pop(identifiant, None)

        # 2. le processus est arrêté et sa mort attendue.
        self._arreter(identifiant, processus)

        # 3. seulement maintenant on peut toucher aux fichiers. C'est l'inversion de cet ordre qui
        #    faisait disparaître le dossier sous la bibliothèque en v1.
        if supprimer_fichiers:
            supprimer(Path(etat.chemin), etat.fichier)
        logger.info("Téléchargement annulé : {} (fichiers supprimés : {})", identifiant, supprimer_fichiers)
        return etat

    def _arreter(self, identifiant: str, processus: BaseProcess | None) -> None:
        """Termine le processus fils, puis s'assure qu'il est bien mort."""
        if processus is None or not processus.is_alive():
            return
        try:
            processus.terminate()
            processus.join(timeout=DELAI_ARRET_S)
            if processus.is_alive():
                logger.warning("Processus {} toujours vivant après terminate, envoi de kill", identifiant)
                processus.kill()
                processus.join(timeout=DELAI_KILL_S)
        except (OSError, ValueError) as exc:
            logger.error("Arrêt du processus de {} problématique : {}", identifiant, exc)

    # --- reprise ------------------------------------------------------------------------------

    def reprendre_interrompus(self) -> list[Telechargement]:
        """À appeler au démarrage : requalifie les transferts que l'arrêt précédent a coupés.

        Rien n'est supprimé et rien n'est relancé automatiquement — c'est un choix : reprendre seul
        un transfert de vingt gigaoctets au démarrage d'un conteneur n'est pas une décision qui
        revient au backend.
        """
        requalifies: list[Telechargement] = []
        for etat in self.lister():
            if not etat.actif or self._vivant(etat.identifiant):
                continue
            recus = octets_recus(Path(etat.chemin), etat.fichier)
            requalifies.append(
                self._muter(
                    etat.identifiant,
                    etat=EtatTelechargement.INTERROMPU,
                    octets_recus=recus,
                    erreur="Le backend s'est arrêté pendant le transfert.",
                    remediation="Relancer le téléchargement : la reprise repart des octets déjà écrits.",
                )
            )
        if requalifies:
            logger.warning("{} téléchargement(s) interrompu(s) retrouvés au démarrage", len(requalifies))
        return requalifies

    def relancer(self, identifiant: str) -> Telechargement:
        """Reprend un téléchargement interrompu, annulé ou en erreur, sans repartir de zéro."""
        courant = self.etat(identifiant)
        return self.demarrer(courant.depot, fichier=courant.fichier, revision=courant.revision)

    # --- diffusion ----------------------------------------------------------------------------

    async def suivre(self, identifiant: str) -> AsyncIterator[Telechargement]:
        """Flux d'états successifs, à brancher tel quel sur une réponse SSE.

        N'émet que sur changement réel et s'arrête sur un état terminal. La borne d'itérations
        garantit qu'un client oublié ne laisse pas une tâche tourner indéfiniment.
        """
        dernier: str | None = None
        for _ in range(MAX_ITERATIONS_DIFFUSION):
            courant = self.etat(identifiant)
            empreinte = courant.model_dump_json()
            if empreinte != dernier:
                dernier = empreinte
                yield courant
            if courant.etat in ETATS_TERMINAUX:
                return
            await asyncio.sleep(INTERVALLE_DIFFUSION_S)
        logger.warning("Diffusion de {} arrêtée sur sa borne d'itérations", identifiant)


@lru_cache(maxsize=1)
def gestionnaire() -> GestionnaireTelechargements:
    """Instance unique du gestionnaire — seul état mutable partagé du domaine, et il est explicite."""
    return GestionnaireTelechargements(JournalTelechargements(dossier_interne()))
