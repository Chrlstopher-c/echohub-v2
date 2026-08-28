"""`/inference/charger` doit refuser un plan dont le moteur n'est plus fonctionnel — même quand le
plan vient déjà construit (`RequeteChargement.plan`), le chemin qui ne repasse jamais par
`choisir_moteur`.

Mesuré le 2026-08-28 : `ggml_cuda_init: failed to initialize CUDA: unknown error` (reproduit dans le
conteneur `echohub-v2` via `docker exec ... llama_supports_gpu_offload()` -> False) rend llama.cpp
`défaillant` en cours de session. `/planifier` le voit (le frontend filtre déjà sur
`moteursUtilisables`), mais un plan déjà construit et rejoué directement contre `/charger` ne
revérifiait rien : un chargement pouvait être accepté (202) sur un moteur mort, puis ne jamais
aboutir — c'est la piste retenue pour le second symptôme (état « chargé » menteur côté mobile).
"""

from __future__ import annotations

import asyncio

import pytest

from backend.core import MoteurIndisponible
from backend.engines.modeles import SanteMoteur, StatutMoteur
from backend.inference import api as domaine_api
from backend.inference.engines_adapters.contrat import MoteurSupporte


def _sante(statut: StatutMoteur, diagnostic: str = "", remediation: str = "") -> SanteMoteur:
    return SanteMoteur(moteur="llamacpp", statut=statut, diagnostic=diagnostic, remediation=remediation)


def test_moteur_defaillant_refuse_avant_le_superviseur(monkeypatch: pytest.MonkeyPatch) -> None:
    appels_superviseur: list[object] = []

    async def sante_cassee() -> SanteMoteur:
        return _sante(
            StatutMoteur.DEFAILLANT,
            diagnostic="Le binaire déclare ne pas supporter l'offload GPU malgré des architectures CUDA compilées.",
            remediation="Reconstruire l'image depuis une base nvidia/cuda:12.8.0-devel et vérifier CMAKE_ARGS.",
        )

    async def demarrer_chargement_espion(plan: object) -> object:
        appels_superviseur.append(plan)
        raise AssertionError("ne doit jamais être atteint : le moteur est défaillant")

    monkeypatch.setattr(domaine_api.engines_service, "sante_llamacpp", sante_cassee)
    monkeypatch.setattr(domaine_api.superviseur, "demarrer_chargement", demarrer_chargement_espion)

    with pytest.raises(MoteurIndisponible) as excinfo:
        asyncio.run(domaine_api._verifier_moteur_disponible(MoteurSupporte.LLAMA_CPP))

    assert excinfo.value.statut_http == 503
    assert appels_superviseur == []


def test_moteur_fonctionnel_laisse_passer(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sante_ok() -> SanteMoteur:
        return _sante(StatutMoteur.FONCTIONNEL)

    monkeypatch.setattr(domaine_api.engines_service, "sante_llamacpp", sante_ok)

    asyncio.run(domaine_api._verifier_moteur_disponible(MoteurSupporte.LLAMA_CPP))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
