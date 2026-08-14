"""Exécution des sondes de diagnostic — brique interne du domaine `engines`.

Une sonde est un script autonome exécuté par un interpréteur donné (celui du backend pour
llama.cpp, celui d'un venv vLLM pour vLLM). Deux raisons de ne jamais la faire tourner dans le
process du backend :

- `llama_cpp` charge une bibliothèque native. Un binaire compilé pour une architecture absente
  peut `abort()` à l'import : dans le backend, l'API entière tombe ; ici, cela devient un code
  retour lisible.
- le venv vLLM contient un autre torch, une autre CUDA et un autre `transformers`. Les importer
  dans le backend est précisément le conflit que l'isolation en venv séparé cherche à éviter.

Les scripts de sonde n'importent donc RIEN du backend — ils s'exécutent dans un environnement où
`backend` n'est pas sur le `sys.path`. Le seul contrat entre eux et ce module est le préfixe
`SENTINELLE_SONDE` : les bibliothèques natives écrivent leurs propres messages sur stdout, la
ligne utile doit être reconnaissable au milieu du bruit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from backend.engines._processus import executer

# Doit rester identique au littéral présent dans chaque script de sonde. La duplication est
# assumée : une sonde ne peut pas importer ce module, elle tourne dans un venv étranger.
SENTINELLE_SONDE = "__ECHOHUB_SONDE__"

# Une sortie de sonde tient en quelques kilo-octets. Au-delà, on ne conserve que la fin, qui est
# l'endroit où se trouve la cause d'un échec.
MAX_SORTIE_CONSERVEE = 8_000


@dataclass(frozen=True)
class ChargeSonde:
    """Retour d'une sonde : la charge JSON si elle a pu être lue, et toujours la sortie brute."""

    donnees: dict[str, object] | None
    sortie_brute: str
    code_retour: int | None
    expire: bool = False

    @property
    def exploitable(self) -> bool:
        return self.donnees is not None


def _extraire_charge(sortie: str) -> dict[str, object] | None:
    """Retient la dernière ligne sentinelle. La dernière, car une sonde peut être relancée."""
    for ligne in reversed(sortie.splitlines()):
        if not ligne.startswith(SENTINELLE_SONDE):
            continue
        brut = ligne[len(SENTINELLE_SONDE) :].strip()
        try:
            charge = json.loads(brut)
        except json.JSONDecodeError as exc:
            logger.error("Charge de sonde illisible : {}", exc)
            return None
        return charge if isinstance(charge, dict) else None
    return None


async def interroger(python: Path, script: Path, *, timeout_s: float) -> ChargeSonde:
    """Exécute `script` avec l'interpréteur `python` et récupère sa charge JSON."""
    if not python.exists():
        logger.warning("Interpréteur de sonde absent : {}", python)
        return ChargeSonde(donnees=None, sortie_brute=f"Interpréteur introuvable : {python}", code_retour=None)

    resultat = await executer([python, script], timeout_s=timeout_s)
    sortie = resultat.sortie[-MAX_SORTIE_CONSERVEE:]
    if resultat.expire:
        logger.warning("Sonde {} expirée après {} s", script.name, timeout_s)
        return ChargeSonde(donnees=None, sortie_brute=sortie, code_retour=None, expire=True)

    donnees = _extraire_charge(resultat.sortie)
    if donnees is None:
        # Pas de ligne sentinelle : la sonde n'est pas allée jusqu'à son `print` final. C'est le
        # cas d'un crash natif — et c'est une information, pas un incident à masquer.
        logger.warning("Sonde {} sans charge exploitable (code {})", script.name, resultat.code_retour)
    return ChargeSonde(donnees=donnees, sortie_brute=sortie, code_retour=resultat.code_retour)
