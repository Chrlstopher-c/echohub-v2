"""État de santé de vLLM : agrégation des venvs et vérification en profondeur.

Deux niveaux de vérité, volontairement distincts parce qu'ils n'ont pas le même coût :

- **l'inventaire** (`venvs.inventaire`) lit le disque et le marqueur. Instantané, il suffit à
  afficher la liste des versions et à savoir laquelle est utilisable ;
- **la vérification** lance la sonde dans chaque venv. Un `import vllm` à froid coûte des dizaines
  de secondes ; on ne la déclenche donc pas à chaque affichage, mais à l'installation (où elle
  conditionne la validation) et sur demande explicite.

Le marqueur conserve le résultat de la vérification faite à l'installation : l'inventaire rapide
n'invente rien, il relit une mesure. C'est la différence avec la v1, qui déduisait « opérationnel »
d'un `pip show` — vert sur un venv où l'import échoue.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from backend.core import MoteurIndisponible
from backend.engines._sonde import interroger
from backend.engines.modeles import DiagnosticVllm, SanteMoteur, StatutMoteur, VersionVllm, maintenant_utc
from backend.engines.vllm import venvs
from backend.engines.vllm.installation import installations_en_cours


async def _verifier_une(etat: VersionVllm) -> VersionVllm:
    """Relance la sonde sur un venv déjà inventorié et remplace ses valeurs par la mesure fraîche."""
    charge = await interroger(etat.python, venvs.SCRIPT_SONDE, timeout_s=venvs.TIMEOUT_SONDE_S)
    if charge.donnees is None:
        motif = "sonde expirée" if charge.expire else "sonde sans réponse exploitable"
        return etat.model_copy(
            update={
                "statut": StatutMoteur.DEFAILLANT,
                "diagnostic": f"Vérification impossible ({motif}) : ce venv ne peut pas être proposé.",
            }
        )
    diagnostic = DiagnosticVllm.model_validate(charge.donnees)
    if not diagnostic.importable:
        return etat.model_copy(
            update={
                "statut": StatutMoteur.DEFAILLANT,
                "diagnostic": f"L'import de vLLM échoue : {diagnostic.erreur}",
            }
        )
    return etat.model_copy(
        update={
            "statut": StatutMoteur.FONCTIONNEL,
            "version_installee": diagnostic.version_vllm,
            "version_transformers": diagnostic.version_transformers,
            "version_torch": diagnostic.version_torch,
            "architectures_gpu": diagnostic.architectures_gpu,
            "diagnostic": _resumer(diagnostic),
        }
    )


def _resumer(diagnostic: DiagnosticVllm) -> str:
    architectures = ", ".join(diagnostic.architectures_gpu) or "aucune"
    return (
        f"vLLM {diagnostic.version_vllm} · torch {diagnostic.version_torch} · "
        f"CUDA {diagnostic.version_cuda} · transformers {diagnostic.version_transformers} · "
        f"architectures {architectures}"
    )


async def inventaire_verifie() -> list[VersionVllm]:
    """Inventaire dont chaque venv marqué valide est reconfirmé par une sonde.

    Séquentiel à dessein : chaque sonde importe torch et vLLM, plusieurs en parallèle feraient
    grimper la RAM sans rien accélérer d'utile.
    """
    verifies: list[VersionVllm] = []
    for etat in venvs.inventaire():
        if etat.statut is StatutMoteur.FONCTIONNEL:
            verifies.append(await _verifier_une(etat))
        else:
            verifies.append(etat)
    return verifies


def version_active(versions: list[VersionVllm]) -> VersionVllm | None:
    """Version retenue par défaut : la plus récente qui soit réellement utilisable."""
    utilisables = [etat for etat in versions if etat.utilisable]
    if not utilisables:
        return None
    return max(utilisables, key=lambda etat: venvs.cle_tri_version(etat.version))


def _details(versions: list[VersionVllm], active: VersionVllm | None) -> dict[str, str]:
    details = {
        "racine": str(venvs.racine()),
        "versions_installees": str(len(versions)),
        "installations_en_cours": ",".join(installations_en_cours()) or "aucune",
    }
    if active is not None:
        details["venv_actif"] = str(active.chemin)
    return details


def sante(versions: list[VersionVllm]) -> SanteMoteur:
    """État de santé agrégé du moteur vLLM, dérivé des venvs présents."""
    active = version_active(versions)
    details = _details(versions, active)
    if active is not None:
        return SanteMoteur(
            moteur="vllm",
            statut=StatutMoteur.FONCTIONNEL,
            version=active.version_installee or active.version,
            architectures_gpu=active.architectures_gpu,
            diagnostic=f"Version active : {active.version}. {active.diagnostic}",
            details=details,
            mesure_le=maintenant_utc(),
        )
    if versions:
        return SanteMoteur(
            moteur="vllm",
            statut=StatutMoteur.INCOMPLET,
            diagnostic="Des venvs vLLM existent mais aucun n'est validé : installations interrompues.",
            remediation="Supprimer les versions incomplètes et relancer une installation.",
            details=details,
            mesure_le=maintenant_utc(),
        )
    return SanteMoteur(
        moteur="vllm",
        statut=StatutMoteur.ABSENT,
        diagnostic="Aucune version de vLLM installée. Le moteur est optionnel : llama.cpp suffit au GGUF.",
        remediation="Installer une version depuis l'écran Système pour servir des modèles safetensors.",
        details=details,
        mesure_le=maintenant_utc(),
    )


def python_de_version(version: str | None = None) -> Path:
    """Interpréteur d'une version utilisable, pour le domaine `inference`.

    Refuse tout venv non validé : c'est ici que se joue le défaut de la v1, où un venv vide était
    remis au chargeur, qui échouait sur un `ModuleNotFoundError` sans explication.
    """
    versions = venvs.inventaire()
    if version is None:
        retenue = version_active(versions)
    else:
        demandee = venvs.valider_version(version)
        retenue = next((etat for etat in versions if etat.version == demandee and etat.utilisable), None)
    if retenue is None:
        logger.warning("Aucun venv vLLM utilisable pour la version demandée : {}", version or "(la plus récente)")
        raise MoteurIndisponible(
            f"Aucune installation vLLM utilisable{f' en version {version}' if version else ''}.",
            remediation="Installer ou réinstaller vLLM depuis l'écran Système avant de charger ce modèle.",
            details={"versions_presentes": [etat.version for etat in versions]},
        )
    return retenue.python
