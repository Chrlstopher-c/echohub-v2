"""État persistant des téléchargements — le fichier qui survit au redémarrage du conteneur.

La v1 gardait ses tâches en mémoire seulement. Un redémarrage effaçait tout : plus de progression,
plus d'historique, et un dossier à moitié rempli que plus personne ne réclamait. Ici l'état est
écrit à chaque transition, à côté des fichiers qu'il décrit.

Le journal vit **dans le répertoire des modèles**, pas dans la base. Deux raisons :

1. il décrit l'état du disque ; s'ils vivaient dans deux volumes différents, restaurer l'un sans
   l'autre produirait exactement le genre d'incohérence qu'on cherche à supprimer ;
2. le schéma SQLite est centralisé dans `core/db` ; un domaine n'y ajoute pas de table de son côté.

L'écriture est atomique (fichier temporaire puis remplacement) : une coupure pendant la
sauvegarde laisse l'ancien journal intact, jamais un JSON tronqué.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field, ValidationError, computed_field

NOM_JOURNAL = "telechargements.json"
SUFFIXE_TEMPORAIRE = ".tmp"


class EtatTelechargement(str, Enum):
    """Cycle de vie d'un téléchargement."""

    EN_ATTENTE = "en_attente"
    EN_COURS = "en_cours"
    TERMINE = "termine"
    ANNULE = "annule"
    # Le processus est mort sans verdict — typiquement l'arrêt du backend. Les octets déjà écrits
    # restent en place : relancer reprend là où ça s'est arrêté.
    INTERROMPU = "interrompu"
    ERREUR = "erreur"


ETATS_ACTIFS = frozenset({EtatTelechargement.EN_ATTENTE, EtatTelechargement.EN_COURS})
ETATS_TERMINAUX = frozenset(set(EtatTelechargement) - ETATS_ACTIFS)


class Telechargement(BaseModel):
    """État d'un téléchargement, tel qu'il est diffusé et tel qu'il est persisté."""

    identifiant: str
    depot: str
    fichier: str | None = None
    revision: str = "main"
    chemin: str
    etat: EtatTelechargement
    octets_recus: int = Field(default=0, ge=0)
    # `None` tant que le Hub n'a pas annoncé les tailles : mieux vaut pas de pourcentage qu'un faux.
    octets_totaux: int | None = None
    erreur: str | None = None
    remediation: str | None = None
    demarre_le: str
    maj_le: str
    termine_le: str | None = None

    @computed_field
    @property
    def progression(self) -> float | None:
        """Fraction transférée, plafonnée à 1, ou `None` si le total est inconnu.

        Le plafond n'est pas cosmétique : la mesure inclut les fragments temporaires, qui coexistent
        brièvement avec le fichier final et feraient dépasser 100 %.
        """
        if not self.octets_totaux:
            return None
        return min(self.octets_recus / self.octets_totaux, 1.0)

    @property
    def actif(self) -> bool:
        return self.etat in ETATS_ACTIFS


class JournalTelechargements:
    """Lecture et écriture atomiques de l'état des téléchargements."""

    def __init__(self, dossier: Path) -> None:
        self._chemin = dossier / NOM_JOURNAL

    @property
    def chemin(self) -> Path:
        return self._chemin

    def charger(self) -> dict[str, Telechargement]:
        """Relit le journal. Un fichier absent, illisible ou corrompu donne un journal vide.

        Repartir de zéro est le comportement voulu : le journal est un index du disque, pas la
        vérité. Les fichiers déjà téléchargés, eux, restent en place.
        """
        if not self._chemin.is_file():
            return {}
        try:
            contenu = json.loads(self._chemin.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Journal des téléchargements illisible ({}), repart à vide : {}", self._chemin, exc)
            return {}
        if not isinstance(contenu, list):
            logger.warning("Journal des téléchargements au format inattendu, repart à vide : {}", self._chemin)
            return {}
        return self._convertir(contenu)

    @staticmethod
    def _convertir(entrees: list[object]) -> dict[str, Telechargement]:
        """Type chaque entrée ; une entrée invalide est écartée sans faire tomber les autres."""
        etats: dict[str, Telechargement] = {}
        for entree in entrees:
            try:
                telechargement = Telechargement.model_validate(entree)
            except ValidationError as exc:
                logger.warning("Entrée de journal ignorée : {}", exc)
                continue
            etats[telechargement.identifiant] = telechargement
        return etats

    def ecrire(self, etats: dict[str, Telechargement]) -> None:
        """Réécrit le journal entier. Une écriture ratée est journalisée, jamais propagée.

        Perdre le journal dégrade le suivi ; faire remonter l'erreur interromprait un téléchargement
        qui se déroule correctement. Le compromis est assumé dans ce sens-là.
        """
        temporaire = self._chemin.with_suffix(self._chemin.suffix + SUFFIXE_TEMPORAIRE)
        charge = [etat.model_dump(mode="json") for etat in etats.values()]
        try:
            self._chemin.parent.mkdir(parents=True, exist_ok=True)
            temporaire.write_text(json.dumps(charge, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporaire, self._chemin)
        except OSError as exc:
            logger.error("Écriture du journal des téléchargements impossible ({}) : {}", self._chemin, exc)
