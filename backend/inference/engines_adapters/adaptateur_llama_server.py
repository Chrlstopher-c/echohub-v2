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
from pydantic import BaseModel, Field

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
        """Relaie le flux SSE, borné par le nombre de tokens : un flux sans fin est un défaut.

        Les appels d'outils ne sont émis qu'À LA CLÔTURE, une fois leurs arguments complets — voir
        `_Accumulateur` pour le défaut que cela corrige.
        """
        charge = self._charge_utile(messages, options, outils)
        plafond = options.max_tokens or (self._etat.contexte if self._etat else 0)
        appels = _Accumulateur()
        raison: str | None = None
        try:
            async with httpx.AsyncClient(timeout=DELAI_GENERATION_S) as client:
                async with client.stream(
                    "POST", f"{serveur.url_base()}/v1/chat/completions", json=charge
                ) as reponse:
                    await _verifier_reponse(reponse)
                    async for morceau, arret in _lire_flux(reponse, appels, plafond):
                        raison = arret or raison
                        if morceau is not None:
                            yield morceau
        except httpx.HTTPError as exc:
            logger.error("Flux llama-server interrompu : {}", exc)
            yield MorceauGeneration(type="erreur", contenu=f"Le moteur a coupé la génération : {exc}")
        if not appels.vide():
            yield MorceauGeneration(type="token", contenu=appels.en_texte())
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


async def _lire_flux(
    reponse: httpx.Response, appels: "_Accumulateur", plafond: int
) -> AsyncIterator[tuple[MorceauGeneration | None, str | None]]:
    """Parcourt les lignes SSE, nourrit l'accumulateur, rend le texte au fil de l'eau.

    Rend des couples (morceau, raison d'arrêt) : la raison arrive souvent sur un événement qui ne
    porte aucun texte, et la perdre ferait attribuer un arrêt sur plafond à une fin naturelle.
    """
    emis = 0
    async for ligne in reponse.aiter_lines():
        delta = _decoder_evenement(ligne)
        if delta is None:
            continue
        if delta.fin:
            yield None, delta.raison_arret
            return
        appels.ajouter(delta.fragments)
        if delta.contenu:
            emis += 1
            yield MorceauGeneration(type="token", contenu=delta.contenu), delta.raison_arret
        else:
            yield None, delta.raison_arret
        if emis >= plafond > 0:
            logger.warning("Flux llama-server borné à {} tokens : arrêt", plafond)
            return


async def _verifier_reponse(reponse: httpx.Response) -> None:
    """Un 4xx/5xx porte la vraie cause dans son corps : le lire avant de lever."""
    if reponse.status_code < 400:
        return
    corps = (await reponse.aread()).decode(errors="replace")
    logger.error("llama-server {} sur /v1/chat/completions : {}", reponse.status_code, corps[:500])
    raise EchecChargement(qualifier(corps, source_verifiee=True),
                          details={"statut": reponse.status_code})


class _Delta(BaseModel):
    """Ce qu'un événement SSE apporte : du texte, et/ou des FRAGMENTS d'appels d'outils."""

    contenu: str = ""
    fragments: list[dict[str, Any]] = Field(default_factory=list)
    raison_arret: str | None = None
    fin: bool = False


def _decoder_evenement(ligne: str) -> _Delta | None:
    """Traduit une ligne SSE en delta. `None` pour tout ce qui n'est pas un événement.

    Fonction PURE et sans état : elle ne sait pas ce qui a précédé, donc elle ne peut pas
    reconstituer un appel d'outil. C'est `_Accumulateur` qui le fait — la séparation est
    délibérée, et c'est exactement ce qui manquait dans la version qui a produit le défaut décrit
    sur `_Accumulateur`.
    """
    if not ligne or not ligne.startswith(PREFIXE_SSE):
        return None
    charge = ligne[len(PREFIXE_SSE):].strip()
    if charge == MARQUEUR_FIN_SSE:
        return _Delta(fin=True)
    try:
        evenement = json.loads(charge)
    except json.JSONDecodeError:
        logger.warning("Événement SSE llama-server illisible, ignoré : {}", charge[:120])
        return None
    choix = (evenement.get("choices") or [{}])[0]
    delta = choix.get("delta") or {}
    # `reasoning_content` est délibérément IGNORÉ : le serveur tourne avec `--reasoning-format
    # none`, qui laisse les balises de réflexion dans `content`. Le lire en plus dupliquerait la
    # réflexion — une fois balisée dans le contenu, une fois nue à côté.
    return _Delta(
        contenu=delta.get("content") or "",
        fragments=list(delta.get("tool_calls") or []),
        raison_arret=choix.get("finish_reason"),
    )


class _Accumulateur:
    """Recompose les appels d'outils émis en morceaux par le flux SSE.

    LE DÉFAUT QU'IL CORRIGE, mesuré en production le 2026-08-26. llama-server envoie les arguments
    d'un appel caractère par caractère :

        {"name":"recherche_web","arguments":"{"}   {"arguments":"\"requete\":\""}
        {"arguments":"met"}   {"arguments":"eo"}   {"arguments":" Paris"}   {"arguments":"}"}

    La première version de cet adaptateur tentait de lire CHAQUE fragment comme un JSON complet.
    `json.loads("{")` lève, le code retombait sur `{}`, et un `<tool_call>` VIDE était émis à
    chaque fragment. Le modèle recevait alors « aucune requête fournie », réessayait, et
    recommençait — six tours identiques observés, tous imputés à tort au modèle alors qu'il avait
    parfaitement produit `{"requete": "meteo Paris demain"}`. Un harnais qui détruit l'appel puis
    reproche son absence est pire qu'un harnais qui échoue : il accuse.

    Les fragments s'accumulent donc par `index` — le flux peut entrelacer plusieurs appels — et ne
    sont lus qu'une fois le flux clos.
    """

    def __init__(self) -> None:
        self._noms: dict[int, str] = {}
        self._arguments: dict[int, list[str]] = {}

    def ajouter(self, fragments: list[dict[str, Any]]) -> None:
        for fragment in fragments:
            index = fragment.get("index")
            if not isinstance(index, int):
                index = 0
            fonction = fragment.get("function") or {}
            nom = fonction.get("name")
            if isinstance(nom, str) and nom:
                self._noms[index] = nom
            morceau = fonction.get("arguments")
            if isinstance(morceau, str) and morceau:
                self._arguments.setdefault(index, []).append(morceau)

    def vide(self) -> bool:
        return not self._noms

    def en_texte(self) -> str:
        """Appels complets, dans la forme `<tool_call>` que la boucle d'outils sait lire.

        Un JSON d'arguments illisible n'est PAS remplacé par `{}` : il repart tel quel au modèle,
        qui verra sa propre production et pourra la corriger. Le remplacer silencieusement était
        précisément le geste qui rendait le défaut invisible.
        """
        morceaux: list[str] = []
        for index in sorted(self._noms):
            brut = "".join(self._arguments.get(index, []))
            charge = json.dumps(
                {"name": self._noms[index], "arguments": _arguments_lus(brut)},
                ensure_ascii=False)
            morceaux.append(f"<tool_call>{charge}</tool_call>")
        return "".join(morceaux)


def _arguments_lus(brut: str) -> Any:
    """Arguments désérialisés, ou la chaîne brute si elle n'est pas du JSON valide."""
    texte = brut.strip()
    if not texte:
        return {}
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        logger.warning("Arguments d'appel illisibles, transmis tels quels : {}", texte[:160])
        return texte


__all__ = ["AdaptateurLlamaServer"]
