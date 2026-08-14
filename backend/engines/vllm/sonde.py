"""Sonde vLLM — script autonome, exécuté par le Python d'un venv vLLM.

N'IMPORTE RIEN DU BACKEND : ce script tourne dans un environnement où `backend` n'existe pas sur
le `sys.path`, et où torch, CUDA et transformers sont dans des versions incompatibles avec celles
du backend. C'est toute la raison d'être du venv séparé.

Ce qu'il mesure :
- `import vllm` aboutit — la seule preuve qu'une installation est réellement utilisable ; la v1
  se contentait de `pip show vllm`, qui reste vert sur un venv où l'import échoue ;
- la version de `transformers` — elle doit être en 5.x, faute de quoi les modèles récents
  échouent au démarrage sur un tokenizer `TokenizersBackend` inconnu (COMPATIBILITE-GPU.md) ;
- l'import de `xgrammar` — ce paquet DÉCLARE exiger `transformers<5`. La borne est trop stricte,
  l'import passe en v5 : c'est mesuré ici, à chaque installation, plutôt que supposé une fois ;
- les architectures GPU compilées dans torch (`sm_75` … `sm_120`), qui ne nécessitent aucun GPU
  présent — ce sont des informations de compilation.

Sortie : une ligne unique sur stdout préfixée par la sentinelle, contenant du JSON.
"""

from __future__ import annotations

import json
import sys

# Doit rester identique à SENTINELLE_SONDE de backend/engines/_sonde.py.
SENTINELLE = "__ECHOHUB_SONDE__"


def _version_paquet(nom: str) -> str | None:
    try:
        import importlib.metadata as metadonnees

        return metadonnees.version(nom)
    except BaseException:  # noqa: BLE001 - paquet absent ou métadonnées corrompues
        return None


def _mesurer_torch(resultat: dict[str, object]) -> None:
    """Renseigne torch, CUDA et les architectures compilées. Aucun GPU requis."""
    try:
        import torch

        resultat["version_torch"] = getattr(torch, "__version__", None)
        resultat["version_cuda"] = getattr(torch.version, "cuda", None)
        architectures = torch.cuda.get_arch_list()
        resultat["architectures_gpu"] = [str(arch) for arch in architectures]
    except BaseException as exc:  # noqa: BLE001 - torch peut échouer à l'import comme au runtime
        resultat["erreur"] = f"torch : {exc}"[:500]
        resultat["type_erreur"] = type(exc).__name__


def _mesurer_vllm(resultat: dict[str, object]) -> None:
    """Import réel de vLLM, puis décompte des architectures de modèles reconnues."""
    try:
        import vllm

        resultat["importable"] = True
        resultat["version_vllm"] = getattr(vllm, "__version__", None) or _version_paquet("vllm")
    except BaseException as exc:  # noqa: BLE001 - import lourd, échecs natifs possibles
        resultat["erreur"] = f"vllm : {exc}"[:500]
        resultat["type_erreur"] = type(exc).__name__
        return
    try:
        from vllm.model_executor.models import ModelRegistry

        resultat["nb_architectures_modeles"] = len(ModelRegistry.get_supported_archs())
    except BaseException:  # noqa: BLE001 - registre interne, son absence n'invalide pas l'install
        resultat["nb_architectures_modeles"] = None


def _mesurer_xgrammar(resultat: dict[str, object]) -> None:
    """Vérifie que la borne `transformers<5` déclarée par xgrammar est bien démentie par l'usage."""
    try:
        import xgrammar  # noqa: F401

        resultat["xgrammar_importable"] = True
    except ImportError:
        resultat["xgrammar_importable"] = False
    except BaseException:  # noqa: BLE001 - échec exotique : l'inconnu vaut mieux qu'un faux vrai
        resultat["xgrammar_importable"] = None


def diagnostiquer() -> dict[str, object]:
    resultat: dict[str, object] = {
        "importable": False,
        "version_vllm": None,
        "version_transformers": _version_paquet("transformers"),
        "version_torch": None,
        "version_cuda": None,
        "xgrammar_importable": None,
        "architectures_gpu": [],
        "nb_architectures_modeles": None,
        "erreur": None,
        "type_erreur": None,
    }
    _mesurer_torch(resultat)
    _mesurer_vllm(resultat)
    _mesurer_xgrammar(resultat)
    return resultat


def main() -> int:
    charge = diagnostiquer()
    sys.stdout.write(f"\n{SENTINELLE}{json.dumps(charge, ensure_ascii=False)}\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
