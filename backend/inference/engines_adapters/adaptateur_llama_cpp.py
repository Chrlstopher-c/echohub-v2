"""Adaptateur llama.cpp — moteur en processus, via llama-cpp-python.

Deux vérifications préalables évitent les deux diagnostics faux les plus coûteux de la v1 :

1. le module est-il présent (sinon : moteur absent, pas fichier illisible) ;
2. le binaire sait-il déléguer au GPU (sinon : moteur compilé sans CUDA — c'est le piège du wheel
   PyPI, CPU-only, où « tout fonctionne » sans que rien ne touche la carte).

Le chargement et la génération sont bloquants : ils partent dans un fil pour ne pas geler la boucle
asyncio, la génération étant en plus sérialisée — une instance `Llama` ne supporte pas deux
générations concurrentes.
"""

from __future__ import annotations

import asyncio
import gc
import os
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, Sequence

from loguru import logger

from backend.inference.engines_adapters.base import AdaptateurMoteur, exiger_moteur, exiger_source_lisible
from backend.inference.engines_adapters.contrat import (
    CauseEchec,
    EtatMoteur,
    MessageChat,
    MorceauGeneration,
    MoteurSupporte,
    OptionsGeneration,
    PlanChargement,
    Sante,
)
from backend.inference.engines_adapters.diagnostic import Diagnostic, EchecChargement, qualifier
from backend.inference.engines_adapters.flux import flux_depuis_bloquant
from backend.inference.engines_adapters.journal import NiveauEntree, SessionChargement, journal_chargement
from backend.inference.engines_adapters.vram import lire_vram

# Identifiants de types GGML acceptés pour le cache KV. Une valeur hors table est un plan invalide :
# la deviner produirait un cache différent de celui que le planificateur a dimensionné.
TYPES_KV: dict[str, int] = {"f32": 0, "f16": 1, "q4_0": 2, "q8_0": 8}

DELAI_VERROU_GENERATION_S = 5.0

# Variable dont la seule présence dégrade gravement le chargement sous WSL2 (mesuré : VRAM figée à
# 2 Go, plusieurs minutes de chargement). Elle n'est jamais posée ici ; si l'environnement la porte
# sans que le plan l'ait demandée, on le signale plutôt que de charger en silence dans ce mode.
VARIABLE_MEMOIRE_UNIFIEE = "GGML_CUDA_ENABLE_UNIFIED_MEMORY"


class AdaptateurLlamaCpp(AdaptateurMoteur):
    """Pilote une instance `Llama` unique, chargée dans le processus du backend."""

    moteur = MoteurSupporte.LLAMA_CPP

    def __init__(self) -> None:
        self._llm: Any | None = None
        self._etat: EtatMoteur | None = None
        self._contexte: int = 0
        # Verrou de fil (pas asyncio) : il protège l'objet C, manipulé depuis les fils de génération.
        self._verrou_generation = threading.Lock()

    @property
    def etat(self) -> EtatMoteur | None:
        return self._etat

    async def charger(self, plan: PlanChargement, session: SessionChargement | None = None) -> EtatMoteur:
        exiger_moteur(plan, self.moteur)
        chemin = exiger_source_lisible(plan)
        module = self._importer(session)
        self._verifier_offload_gpu(module, plan, session)
        self._appliquer_environnement(plan, session)

        parametres = self._parametres(plan, chemin)
        vram_avant = lire_vram()
        journal_chargement.noter(
            session, "llama.cpp", f"Chargement de {plan.nom_affiche}",
            details={"parametres": {c: v for c, v in parametres.items() if c != "model_path"},
                     "vram_libre_mo": vram_avant.libre_mo if vram_avant else None},
        )

        debut = time.perf_counter()
        self._llm = await self._instancier(module, parametres, session)
        duree = time.perf_counter() - debut
        vram_apres = lire_vram()
        self._contexte = plan.contexte
        self._etat = EtatMoteur(
            moteur=self.moteur, modele=plan.nom_affiche, pret=True,
            contexte=plan.contexte, couches_gpu=plan.couches_gpu, duree_chargement_s=round(duree, 2),
            vram_avant_octets=vram_avant.utilisee_octets if vram_avant else None,
            vram_apres_octets=vram_apres.utilisee_octets if vram_apres else None,
        )
        journal_chargement.noter(
            session, "llama.cpp", f"Modèle prêt en {duree:.1f} s",
            details={"vram_utilisee_mo": vram_apres.utilisee_mo if vram_apres else None},
        )
        return self._etat

    async def _instancier(self, module: Any, parametres: dict[str, Any], session: SessionChargement | None) -> Any:
        """Construit l'instance dans un fil. Toute exception est qualifiée, jamais remontée nue.

        Une annulation pendant ce chargement ne l'interrompt pas — llama.cpp charge en C, sans point
        d'annulation. Le fil finit son travail ; l'instance produite n'étant référencée nulle part,
        elle est collectée et sa VRAM rendue peu après.
        """
        try:
            return await asyncio.to_thread(lambda: module.Llama(**parametres))
        except Exception as exc:
            # `source_verifiee` : la lisibilité du GGUF a déjà été contrôlée, le fichier est hors de cause.
            diagnostic = qualifier(str(exc), source_verifiee=True, exception=exc)
            journal_chargement.noter(
                session, "llama.cpp", f"Échec : {diagnostic.message}",
                niveau=NiveauEntree.ERREUR, details={"cause": diagnostic.cause.value},
            )
            raise EchecChargement(diagnostic, details={"moteur": self.moteur.value}) from exc

    def _importer(self, session: SessionChargement | None) -> Any:
        try:
            import llama_cpp
        except ImportError as exc:
            journal_chargement.noter(
                session, "llama.cpp", "Module llama_cpp introuvable", niveau=NiveauEntree.ERREUR,
            )
            raise EchecChargement(
                Diagnostic(
                    cause=CauseEchec.MOTEUR_ABSENT,
                    message="llama-cpp-python n'est pas installé dans l'environnement du backend.",
                    remediation="Installer le moteur depuis l'écran Système avant de charger un modèle.",
                    indices={"import": str(exc)},
                )
            ) from exc
        return llama_cpp

    def _verifier_offload_gpu(self, module: Any, plan: PlanChargement, session: SessionChargement | None) -> None:
        """Un plan qui délègue au GPU exige un binaire compilé avec CUDA — sinon l'échec est muet."""
        if plan.couches_gpu == 0:
            return
        sonde = getattr(module, "llama_supports_gpu_offload", None)
        if sonde is None:
            journal_chargement.noter(
                session, "llama.cpp", "Version trop ancienne pour déclarer son support GPU : non vérifié",
                niveau=NiveauEntree.AVERTISSEMENT,
            )
            return
        try:
            supporte = bool(sonde())
        except Exception as exc:
            logger.warning("Sonde de support GPU llama.cpp inutilisable : {}", exc)
            return
        if not supporte:
            raise EchecChargement(
                Diagnostic(
                    cause=CauseEchec.MOTEUR_SANS_CUDA,
                    message="llama-cpp-python est installé sans support CUDA : aucune couche ne peut aller au GPU.",
                    remediation="Réinstaller avec --no-binary et CMAKE_ARGS=-DGGML_CUDA=on : "
                                "le wheel PyPI par défaut est CPU-only.",
                    indices={"couches_gpu_demandees": plan.couches_gpu},
                )
            )

    def _appliquer_environnement(self, plan: PlanChargement, session: SessionChargement | None) -> None:
        """Pose les variables du plan. Le moteur étant en processus, elles restent pour sa durée de vie."""
        for cle, valeur in plan.variables_env.items():
            os.environ[cle] = valeur
        if VARIABLE_MEMOIRE_UNIFIEE in os.environ and VARIABLE_MEMOIRE_UNIFIEE not in plan.variables_env:
            journal_chargement.noter(
                session, "llama.cpp",
                f"{VARIABLE_MEMOIRE_UNIFIEE} présente dans l'environnement sans être au plan : "
                "sous WSL2 elle fige la VRAM et rend le modèle inutilisable.",
                niveau=NiveauEntree.AVERTISSEMENT,
            )

    def _parametres(self, plan: PlanChargement, chemin: Path) -> dict[str, Any]:
        """Traduit le plan en arguments `Llama`. Aucune valeur n'est inventée ici."""
        parametres: dict[str, Any] = {
            "model_path": str(chemin),
            "n_ctx": plan.contexte,
            "n_batch": plan.batch,
            "n_gpu_layers": plan.couches_gpu,
            "verbose": False,
        }
        if plan.flash_attention is not None:
            parametres["flash_attn"] = plan.flash_attention
        if plan.type_kv_cache is not None:
            identifiant = TYPES_KV.get(plan.type_kv_cache.lower())
            if identifiant is None:
                raise EchecChargement(
                    Diagnostic(
                        cause=CauseEchec.PLAN_INCOMPLET,
                        message=f"Type de cache KV inconnu : {plan.type_kv_cache}.",
                        remediation=f"Valeurs acceptées : {', '.join(sorted(TYPES_KV))}.",
                    )
                )
            parametres["type_k"] = identifiant
            parametres["type_v"] = identifiant
        return parametres

    async def decharger(self) -> None:
        """Libère l'instance et force un cycle GC : la VRAM part avec l'objet C, pas avant."""
        if self._llm is None:
            self._etat = None
            return
        instance, self._llm, self._etat = self._llm, None, None
        try:
            fermer = getattr(instance, "close", None)
            if callable(fermer):
                await asyncio.to_thread(fermer)
        except Exception as exc:
            logger.warning("Fermeture llama.cpp imparfaite : {}", exc)
        finally:
            del instance
            gc.collect()
            logger.info("llama.cpp déchargé")

    async def sante(self) -> Sante:
        if self._llm is None or self._etat is None:
            return Sante(disponible=False, moteur=self.moteur, detail="Aucun modèle chargé.")
        debut = time.perf_counter()
        try:
            contexte = await asyncio.to_thread(self._llm.n_ctx)
        except Exception as exc:
            logger.error("Sonde llama.cpp en échec : {}", exc)
            return Sante(disponible=False, moteur=self.moteur, modele=self._etat.modele, detail=str(exc))
        latence = (time.perf_counter() - debut) * 1000
        return Sante(
            disponible=True, moteur=self.moteur, modele=self._etat.modele,
            latence_ms=round(latence, 2), detail=f"contexte servi : {contexte}",
        )

    def generer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
    ) -> AsyncIterator[MorceauGeneration]:
        if self._llm is None:
            raise EchecChargement(
                Diagnostic(
                    cause=CauseEchec.MOTEUR_ABSENT,
                    message="Aucun modèle chargé dans llama.cpp.",
                    remediation="Charger un modèle avant de générer.",
                )
            )
        plafond = options.max_tokens or self._contexte
        return flux_depuis_bloquant(
            lambda arret: self._iterer(messages, options, arret),
            iterations_max=plafond + 1,  # +1 : le morceau de fin n'est pas un token
        )

    def _iterer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
        arret: threading.Event,
    ) -> Iterator[MorceauGeneration]:
        """Boucle bloquante exécutée dans un fil, sous verrou : une génération à la fois."""
        if not self._verrou_generation.acquire(timeout=DELAI_VERROU_GENERATION_S):
            raise RuntimeError("Une génération est déjà en cours sur ce modèle.")
        try:
            flux = self._llm.create_chat_completion(  # type: ignore[union-attr]
                messages=[message.model_dump() for message in messages],
                stream=True,
                **_arguments_echantillonnage(options),
            )
            raison: str | None = None
            for morceau in flux:
                if arret.is_set():
                    raison = "annule"
                    break
                choix = (morceau.get("choices") or [{}])[0]
                raison = choix.get("finish_reason") or raison
                contenu = (choix.get("delta") or {}).get("content") or ""
                if contenu:
                    yield MorceauGeneration(type="token", contenu=contenu)
            yield MorceauGeneration(type="fin", raison_arret=raison)
        finally:
            self._verrou_generation.release()


def _arguments_echantillonnage(options: OptionsGeneration) -> dict[str, Any]:
    """Ne transmet que les réglages explicitement demandés : le reste reste au défaut du moteur."""
    arguments: dict[str, Any] = {"temperature": options.temperature, "top_p": options.top_p}
    if options.top_k is not None:
        arguments["top_k"] = options.top_k
    if options.repetition_penalty is not None:
        arguments["repeat_penalty"] = options.repetition_penalty
    if options.max_tokens is not None:
        arguments["max_tokens"] = options.max_tokens
    if options.stop:
        arguments["stop"] = list(options.stop)
    if options.graine is not None:
        arguments["seed"] = options.graine
    return arguments
