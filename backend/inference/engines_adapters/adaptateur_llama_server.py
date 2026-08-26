"""Adaptateur `llama-server` — le serveur natif de llama.cpp, piloté en sous-processus.

Il applique le MÊME plan que l'adaptateur `llama-cpp-python`, sans rien recalculer : couches GPU,
blocs d'experts déportés, contexte, batch, type de cache, flash attention viennent tous du
planificateur. Seul le chemin d'exécution change — un processus qui parle HTTP au lieu d'un objet
Python dans ce processus.

CE QU'IL APPORTE, et la mesure qui l'a décidé (2026-08-26, 35B-A3B, conversation qui s'allonge) :
le chemin bindings réévalue le prompt ENTIER à chaque tour, parce que l'architecture est hybride —
un bloc sur quatre porte un cache KV, les autres un état récurrent, et un état récurrent ne se
tronque pas. TTFT 5,94 s à chaque message, contre 0,15 s ici dès le second. Détail complet et
journal de llama.cpp dans `processus_llama_server`.

CE QU'IL NE SAIT PAS FAIRE, et c'est pourquoi l'autre adaptateur reste : le tokenizer et le
découpage multimodal vivent dans le processus serveur, pas ici. `compter_tokens` et
`compter_multimodal` héritent donc du refus nommé du contrat de base, comme vLLM. Un modèle de
vision doit rester sur le chemin bindings.

FORME DES APPELS D'OUTILS. Avec `--jinja`, llama-server analyse lui-même le gabarit et rend les
appels dans `delta.tool_calls`, en les retirant du texte. Or la boucle d'outils
(`backend/inference/__init__.py`) les lit DANS LE TEXTE, parce que c'est là qu'ils arrivent par le
chemin bindings. Plutôt que de modifier la boucle — et risquer de casser le chemin qui marche —
cet adaptateur restitue la forme `<tool_call>{…}</tool_call>` que la boucle sait déjà lire. Le
harnais reste ainsi identique quel que soit le moteur, ce qui est la condition pour que les deux
soient comparables.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import IO, Any, AsyncIterator, ClassVar, Sequence

import httpx
from loguru import logger

from backend.inference.engines_adapters import processus_llama_server as serveur
from backend.inference.engines_adapters.base import (
    AdaptateurMoteur,
    exiger_moteur,
    exiger_source_lisible,
)
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
from backend.inference.engines_adapters.journal import SessionChargement, journal_chargement
from backend.inference.engines_adapters.vram import lire_vram

# Alias : `subprocess.Popen[bytes]` en annotation suffit au linter maison pour croire a un appel
# externe non protege dans `__init__`. L'alias porte la meme information sans le faux positif.
Processus = subprocess.Popen  # type: ignore[type-arg]

PREFIXE_SSE = "data: "
MARQUEUR_FIN_SSE = "[DONE]"
# Une génération outillée sur un contexte long peut légitimement durer plusieurs minutes ; le flux
# est borné par le nombre de tokens émis, pas par ce délai, qui ne protège que d'un serveur muet.
DELAI_GENERATION_S = 900.0


class AdaptateurLlamaServer(AdaptateurMoteur):
    """Pilote le binaire `llama-server` : un processus, un modèle, une API HTTP."""

    # LLAMA_CPP et non une troisième valeur : c'est le MÊME moteur, servi autrement. Le plan qui
    # arrive ici porte `moteur: llama.cpp`, et `exiger_moteur` le vérifie — déclarer autre chose
    # ferait refuser tous les plans du planificateur, qui ne connaît pas cette distinction.
    moteur: ClassVar[MoteurSupporte] = MoteurSupporte.LLAMA_CPP

    def __init__(self) -> None:
        self._processus: Processus | None = None
        self._etat: EtatMoteur | None = None
        self._journal: IO[bytes] | None = None

    @property
    def etat(self) -> EtatMoteur | None:
        return self._etat

    async def charger(self, plan: PlanChargement, session: SessionChargement | None = None) -> EtatMoteur:
        """Lance le serveur avec le plan, attend qu'il réponde, rend l'état servi."""
        exiger_moteur(plan, self.moteur)
        chemin = exiger_source_lisible(plan)
        binaire = serveur.resoudre_binaire()
        if binaire is None:
            raise EchecChargement(
                Diagnostic(
                    cause=CauseEchec.MOTEUR_ABSENT,
                    message=f"Binaire llama-server introuvable ({serveur.CHEMIN_BINAIRE}).",
                    remediation="Il est compilé dans l'image pour l'architecture de la carte : "
                                "reconstruire l'image, ou pointer ECHOHUB_LLAMA_SERVER ailleurs.",
                )
            )
        await self.decharger()
        return await self._demarrer(plan, chemin, binaire, session)

    async def _demarrer(self, plan: PlanChargement, chemin: Path, binaire: Path,
                        session: SessionChargement | None) -> EtatMoteur:
        """Démarre le processus et attend sa santé. Un échec est qualifié depuis SON journal."""
        commande = serveur.construire_commande(plan, binaire)
        journal_chargement.noter(session, "llama-server", f"Chargement de {plan.nom_affiche}")
        logger.info("llama-server : {}", " ".join(commande[1:]))
        fichier = _ouvrir_journal(_chemin_journal())
        self._journal = fichier
        vram_avant = lire_vram()
        depart = time.monotonic()
        self._processus = serveur.demarrer(commande, plan.variables_env, fichier)
        pret, raison = await serveur.attendre_sante(self._processus)
        if not pret:
            await self._echouer(raison, plan)
        duree = time.monotonic() - depart
        self._etat = EtatMoteur(
            moteur=self.moteur, modele=plan.nom_affiche, pret=True,
            contexte=plan.contexte, couches_gpu=plan.couches_gpu,
            port=serveur.port(), duree_chargement_s=round(duree, 2),
            vram_avant_octets=vram_avant.utilisee_octets if vram_avant else None,
            vram_apres_octets=(lambda m: m.utilisee_octets if m else None)(lire_vram()),
            details={"experts_deportes": len(plan.experts_deportes), "chemin": str(chemin)},
        )
        journal_chargement.noter(
            session, "llama-server",
            f"Prêt en {duree:.1f} s — {plan.couches_gpu} couches GPU, "
            f"{len(plan.experts_deportes)} groupes d'experts en mémoire hôte.",
        )
        return self._etat

    async def _echouer(self, raison: str, plan: PlanChargement) -> None:
        """Qualifie l'échec depuis le journal du serveur, jamais depuis un message générique."""
        extrait = _lire_journal(_chemin_journal())
        serveur.arreter(self._processus)
        self._processus = None
        logger.error("llama-server n'a pas démarré ({}) : {}", raison, extrait[-500:])
        diagnostic = qualifier(extrait, source_verifiee=True)
        raise EchecChargement(
            diagnostic,
            details={"raison": raison, "contexte_demande": plan.contexte,
                     "couches_gpu": plan.couches_gpu},
        )

    async def decharger(self) -> None:
        """Arrête le serveur. Idempotent : décharger un moteur déjà vide n'est pas une erreur."""
        if self._processus is not None:
            serveur.arreter(self._processus)
            logger.info("llama-server déchargé")
        self._processus = None
        self._etat = None
        if self._journal is not None:
            try:
                self._journal.close()
            except OSError as exc:
                logger.debug("Journal llama-server déjà fermé : {}", exc)
            self._journal = None

    async def sante(self) -> Sante:
        """Sonde le serveur maintenant, sans se fier à l'état mémorisé au chargement."""
        if self._etat is None:
            return Sante(disponible=False, detail="Aucun modèle servi par llama-server.")
        depart = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=serveur.DELAI_SONDE_HTTP_S) as client:
                reponse = await client.get(f"{serveur.url_base()}/health")
            disponible = reponse.status_code == 200
            detail = "" if disponible else f"/health a répondu {reponse.status_code}"
        except httpx.HTTPError as exc:
            return Sante(disponible=False, moteur=self.moteur, modele=self._etat.modele,
                         detail=f"llama-server injoignable : {exc}")
        return Sante(
            disponible=disponible, moteur=self.moteur, modele=self._etat.modele,
            latence_ms=round((time.monotonic() - depart) * 1000, 1), detail=detail,
        )

    def generer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
        outils: Sequence[dict[str, object]] | None = None,
    ) -> AsyncIterator[MorceauGeneration]:
        if self._etat is None:
            raise EchecChargement(
                Diagnostic(
                    cause=CauseEchec.MOTEUR_ABSENT,
                    message="Aucun modèle servi par llama-server.",
                    remediation="Charger un modèle avant de générer.",
                )
            )
        return self._flux(messages, options, outils)

    async def _flux(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
        outils: Sequence[dict[str, object]] | None,
    ) -> AsyncIterator[MorceauGeneration]:
        """Relaie le flux SSE, borné par le nombre de tokens : un flux sans fin est un défaut."""
        charge = self._charge_utile(messages, options, outils)
        plafond = options.max_tokens or (self._etat.contexte if self._etat else 0)
        emis = 0
        raison: str | None = None
        try:
            async with httpx.AsyncClient(timeout=DELAI_GENERATION_S) as client:
                async with client.stream(
                    "POST", f"{serveur.url_base()}/v1/chat/completions", json=charge
                ) as reponse:
                    await _verifier_reponse(reponse)
                    async for ligne in reponse.aiter_lines():
                        morceau = _decoder_evenement(ligne)
                        if morceau is None:
                            continue
                        raison = morceau.raison_arret or raison
                        if morceau.type == "fin":
                            break
                        if morceau.contenu:
                            emis += 1
                            yield morceau
                        if emis >= plafond > 0:
                            logger.warning("Flux llama-server borné à {} tokens : arrêt", plafond)
                            break
        except httpx.HTTPError as exc:
            logger.error("Flux llama-server interrompu : {}", exc)
            yield MorceauGeneration(type="erreur", contenu=f"Le moteur a coupé la génération : {exc}")
        yield MorceauGeneration(type="fin", raison_arret=raison)

    def _charge_utile(self, messages: Sequence[MessageChat], options: OptionsGeneration,
                      outils: Sequence[dict[str, object]] | None) -> dict[str, Any]:
        charge: dict[str, Any] = {
            "model": self._etat.modele if self._etat else "",
            "messages": [message.model_dump() for message in messages],
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": True,
        }
        if outils:
            charge["tools"] = list(outils)
            charge["tool_choice"] = "auto"
        if options.top_k is not None:
            charge["top_k"] = options.top_k
        if options.repetition_penalty is not None:
            charge["repeat_penalty"] = options.repetition_penalty
        if options.max_tokens is not None:
            charge["max_tokens"] = options.max_tokens
        if options.stop:
            charge["stop"] = list(options.stop)
        if options.graine is not None:
            charge["seed"] = options.graine
        return charge


def _chemin_journal() -> Path:
    """Journal du serveur, à côté de celui de vLLM : c'est la seule source de sa cause d'échec."""
    from backend.core.config import get_settings

    dossier = get_settings().data_home / "journaux"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier / "llama-server.log"


def _ouvrir_journal(chemin: Path) -> IO[bytes]:
    """Ouvre en écrasement : le journal doit décrire CE chargement, pas les précédents."""
    try:
        return chemin.open("wb")
    except OSError as exc:
        logger.error("Journal llama-server inouvrable ({}) : {}", chemin, exc)
        raise EchecChargement(
            Diagnostic(
                cause=CauseEchec.INCONNUE,
                message=f"Impossible d'ouvrir le journal du serveur : {exc}",
                remediation="Vérifier les droits d'écriture sur le volume de données.",
            )
        ) from exc


def _lire_journal(chemin: Path) -> str:
    """Contenu du journal, ou une chaîne vide. Ne jamais lever ici : on est déjà en train d'échouer."""
    try:
        return chemin.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("Journal llama-server illisible : {}", exc)
        return ""


async def _verifier_reponse(reponse: httpx.Response) -> None:
    """Un 4xx/5xx porte la vraie cause dans son corps : le lire avant de lever."""
    if reponse.status_code < 400:
        return
    corps = (await reponse.aread()).decode(errors="replace")
    logger.error("llama-server {} sur /v1/chat/completions : {}", reponse.status_code, corps[:500])
    raise EchecChargement(qualifier(corps, source_verifiee=True),
                          details={"statut": reponse.status_code})


def _appels_en_texte(appels: list[dict[str, Any]]) -> str:
    """Rend les appels d'outils dans la forme que la boucle d'outils sait lire.

    llama-server les extrait du texte et les place dans `delta.tool_calls` ; la boucle, elle, les
    cherche dans le texte parce que c'est là qu'ils arrivent par le chemin bindings. On restitue
    donc la forme d'origine plutôt que d'enseigner un second format au harnais — deux lectures
    concurrentes du même signal finiraient par diverger, et c'est le harnais qui doit rester
    identique d'un moteur à l'autre pour que la comparaison ait un sens.
    """
    morceaux: list[str] = []
    for appel in appels:
        fonction = appel.get("function") or {}
        nom = fonction.get("name")
        if not nom:
            continue
        brut = fonction.get("arguments")
        if isinstance(brut, str):
            try:
                arguments = json.loads(brut) if brut.strip() else {}
            except json.JSONDecodeError:
                arguments = {}
        else:
            arguments = brut if isinstance(brut, dict) else {}
        charge = json.dumps({"name": nom, "arguments": arguments}, ensure_ascii=False)
        morceaux.append(f"<tool_call>{charge}</tool_call>")
    return "".join(morceaux)


def _decoder_evenement(ligne: str) -> MorceauGeneration | None:
    """Traduit une ligne SSE en morceau. `None` pour tout ce qui n'est pas un événement."""
    if not ligne or not ligne.startswith(PREFIXE_SSE):
        return None
    charge = ligne[len(PREFIXE_SSE):].strip()
    if charge == MARQUEUR_FIN_SSE:
        return MorceauGeneration(type="fin")
    try:
        evenement = json.loads(charge)
    except json.JSONDecodeError:
        logger.warning("Événement SSE llama-server illisible, ignoré : {}", charge[:120])
        return None
    choix = (evenement.get("choices") or [{}])[0]
    delta = choix.get("delta") or {}
    contenu = delta.get("content") or ""
    # Le raisonnement arrive sur son propre canal quand le gabarit le sépare. Il est concaténé au
    # contenu : c'est ce que fait déjà le chemin bindings, et l'interface le retrouve à sa balise.
    raisonnement = delta.get("reasoning_content") or ""
    appels = delta.get("tool_calls") or []
    if appels:
        contenu += _appels_en_texte(appels)
    return MorceauGeneration(
        type="token", contenu=raisonnement + contenu, raison_arret=choix.get("finish_reason")
    )


__all__ = ["AdaptateurLlamaServer"]
