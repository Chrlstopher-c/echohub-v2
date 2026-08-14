"""Exécution de sous-processus bornée — brique interne du domaine `engines`.

Tout ce que ce domaine fait de coûteux passe par un process externe : `python -m venv`, `pip
install`, et les sondes de diagnostic. Deux propriétés sont exigées ici et nulle part ailleurs :

1. **Aucune attente non bornée.** Un `pip install` qui ne rend jamais la main gèlerait la requête
   HTTP qui consomme le flux. Chaque exécution porte une échéance et un plafond de lignes lues.
2. **Interruption effective.** Une annulation ne peut pas se contenter de cesser de lire : le
   process doit être terminé, sinon un pip continue de peupler un venv que l'on vient de déclarer
   abandonné — et le venv à moitié construit réapparaît au redémarrage.

Ce module ne connaît ni vLLM ni llama.cpp : il ne manipule que des commandes et des lignes.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

# Plafond de lignes remontées par une exécution. Un pip verbeux tient largement en dessous ; au
# delà, la sortie est un emballement (boucle de retry, barre de progression non désactivée) et
# continuer à la relayer noierait l'interface.
MAX_LIGNES = 20_000

# Délai laissé à un process pour sortir sur SIGTERM avant le SIGKILL.
DELAI_ARRET_S = 10.0


class ProcessusAnnule(RuntimeError):
    """L'appelant a demandé l'annulation ; le process a été terminé."""


class ProcessusExpire(RuntimeError):
    """L'échéance a été atteinte ; le process a été terminé."""


@dataclass(frozen=True)
class ResultatProcessus:
    """Sortie complète d'une exécution courte (sonde, commande ponctuelle)."""

    code_retour: int | None
    sortie: str
    expire: bool = False
    echec_lancement: bool = False

    @property
    def reussi(self) -> bool:
        return self.code_retour == 0 and not self.expire and not self.echec_lancement


def environnement_process(supplements: dict[str, str] | None = None) -> dict[str, str]:
    """Environnement des sous-processus : celui du backend, plus des réglages non négociables.

    `PYTHONUNBUFFERED` est indispensable au flux : sans lui, la sortie de pip est tamponnée et
    l'interface ne voit rien pendant vingt minutes, puis tout d'un coup.
    """
    environnement = dict(os.environ)
    environnement.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
        }
    )
    environnement.update(supplements or {})
    return environnement


async def _terminer(processus: asyncio.subprocess.Process) -> None:
    """Termine un process encore vivant. SIGTERM puis, à échéance, SIGKILL — jamais d'attente nue."""
    if processus.returncode is not None:
        return
    try:
        processus.terminate()
        await asyncio.wait_for(processus.wait(), timeout=DELAI_ARRET_S)
        return
    except asyncio.TimeoutError:
        logger.warning("Process {} insensible à SIGTERM, passage en SIGKILL", processus.pid)
    except ProcessLookupError:
        return
    except OSError as exc:
        logger.warning("Arrêt du process {} impossible : {}", processus.pid, exc)
        return
    try:
        processus.kill()
        await asyncio.wait_for(processus.wait(), timeout=DELAI_ARRET_S)
    except (asyncio.TimeoutError, ProcessLookupError, OSError) as exc:
        logger.error("Process {} non récupérable après SIGKILL : {}", processus.pid, exc)


async def executer(
    commande: Sequence[str | Path],
    *,
    timeout_s: float,
    environnement: dict[str, str] | None = None,
) -> ResultatProcessus:
    """Exécute une commande courte et retourne sa sortie complète. N'échoue jamais par exception."""
    arguments = [str(element) for element in commande]
    try:
        processus = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=environnement or environnement_process(),
        )
    except (OSError, ValueError) as exc:
        logger.error("Lancement impossible de {} : {}", arguments[0], exc)
        return ResultatProcessus(code_retour=None, sortie=str(exc), echec_lancement=True)

    try:
        sortie, _ = await asyncio.wait_for(processus.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning("Commande expirée après {} s : {}", timeout_s, arguments[0])
        await _terminer(processus)
        return ResultatProcessus(code_retour=None, sortie="", expire=True)

    return ResultatProcessus(
        code_retour=processus.returncode,
        sortie=sortie.decode("utf-8", errors="replace"),
    )


@dataclass
class FluxProcessus:
    """Sous-processus long dont la sortie est relayée ligne à ligne, sous double borne.

    Usage : `async for ligne in flux.lignes(): ...` puis lecture de `code_retour`. Une annulation
    ou une expiration lève, respectivement, `ProcessusAnnule` ou `ProcessusExpire` — dans les deux
    cas le process est terminé avant que l'exception ne remonte.
    """

    commande: Sequence[str | Path]
    timeout_s: float
    annulation: asyncio.Event | None = None
    environnement: dict[str, str] | None = None
    max_lignes: int = MAX_LIGNES
    code_retour: int | None = field(default=None, init=False)
    _processus: asyncio.subprocess.Process | None = field(default=None, init=False, repr=False)

    def tuer(self) -> None:
        """Arrêt immédiat et **synchrone** du process, sans passer par SIGTERM.

        Existe pour être appelable depuis un `finally` de nettoyage, là où l'on ne peut compter
        sur aucun `await` : quand un générateur asynchrone imbriqué est abandonné, sa finalisation
        est remise au ramasse-miettes. S'en remettre à elle laisserait un `pip install` continuer
        de peupler un venv que l'on est en train de supprimer.
        """
        processus = self._processus
        if processus is None or processus.returncode is not None:
            return
        try:
            processus.kill()
            logger.warning("Process {} tué pendant le nettoyage d'une installation", processus.pid)
        except (ProcessLookupError, OSError) as exc:
            logger.warning("Arrêt immédiat du process impossible : {}", exc)

    async def lignes(self) -> AsyncIterator[str]:
        """Relaie la sortie fusionnée (stdout + stderr) du process jusqu'à sa fin."""
        arguments = [str(element) for element in self.commande]
        try:
            processus = await asyncio.create_subprocess_exec(
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=self.environnement or environnement_process(),
            )
        except (OSError, ValueError) as exc:
            logger.error("Lancement impossible de {} : {}", arguments[0], exc)
            raise ProcessusExpire(f"Commande introuvable ou non exécutable : {arguments[0]} ({exc})") from exc

        self._processus = processus
        echeance = asyncio.get_running_loop().time() + self.timeout_s
        try:
            async for ligne in self._lire(processus, echeance):
                yield ligne
            self.code_retour = await self._attendre_fin(processus, echeance)
        finally:
            # Couvre aussi la fermeture prématurée du générateur (client SSE déconnecté) : sans ce
            # bloc, le pip continuerait de remplir un venv que l'appelant a abandonné.
            await _terminer(processus)

    async def _lire(self, processus: asyncio.subprocess.Process, echeance: float) -> AsyncIterator[str]:
        if processus.stdout is None:
            raise ProcessusExpire("Sortie standard du process indisponible.")
        lues = 0
        while lues < self.max_lignes:
            ligne = await self._prochaine_ligne(processus.stdout, echeance)
            if ligne is None:
                return
            lues += 1
            yield ligne
        logger.warning("Plafond de {} lignes atteint, sortie tronquée : {}", self.max_lignes, self.commande[0])

    async def _prochaine_ligne(self, flux: asyncio.StreamReader, echeance: float) -> str | None:
        """Prochaine ligne, ou `None` en fin de flux. Course entre lecture, annulation et échéance."""
        restant = echeance - asyncio.get_running_loop().time()
        if restant <= 0:
            raise ProcessusExpire(f"Échéance de {self.timeout_s} s dépassée.")

        tache_ligne: asyncio.Task[bytes] = asyncio.ensure_future(flux.readline())
        taches: list[asyncio.Task[object]] = [tache_ligne]
        tache_annulation: asyncio.Task[bool] | None = None
        if self.annulation is not None:
            tache_annulation = asyncio.ensure_future(self.annulation.wait())
            taches.append(tache_annulation)

        terminees, en_attente = await asyncio.wait(taches, timeout=restant, return_when=asyncio.FIRST_COMPLETED)
        for tache in en_attente:
            tache.cancel()

        if tache_annulation is not None and tache_annulation in terminees:
            raise ProcessusAnnule("Annulation demandée.")
        if tache_ligne not in terminees:
            raise ProcessusExpire(f"Échéance de {self.timeout_s} s dépassée.")

        brut: bytes = tache_ligne.result()
        if not brut:
            return None
        return brut.decode("utf-8", errors="replace").rstrip()

    async def _attendre_fin(self, processus: asyncio.subprocess.Process, echeance: float) -> int | None:
        restant = max(echeance - asyncio.get_running_loop().time(), 0.0)
        try:
            return await asyncio.wait_for(processus.wait(), timeout=max(restant, DELAI_ARRET_S))
        except asyncio.TimeoutError as exc:
            raise ProcessusExpire(f"Le process n'a pas rendu la main après {self.timeout_s} s.") from exc
