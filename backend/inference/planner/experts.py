"""Déport des tenseurs d'experts vers la mémoire hôte — le bon axe de placement d'un MoE.

POURQUOI CE MODULE EXISTE. Mesuré sur Qwen3.6-35B-A3B IQ3_M (733 tenseurs, 40 blocs) : les
120 tenseurs `ffn_{gate,up,down}_exps` pèsent 13,057 Gio, soit **90,9 % du fichier**, tandis que
tout le reste d'un bloc — attention, état récurrent, normes, routeur, expert partagé — pèse 15,68 à
19,50 Mio. Or 8 experts sur 256 seulement sont lus par token.

Couper par couches entières est donc le mauvais axe : sortir une couche de la VRAM fait payer au CPU
19,5 Mio de dense **lus intégralement à chaque token** pour libérer 335 Mio d'experts dont 10,5 Mio
sont lus. Le plan 29/40 mesuré coûte ainsi 11 x (19,5 + 10,5) = 330 Mio de trafic hôte par token.
Déporter 4 groupes d'experts libère autant de VRAM pour 4 x 10,5 = 42 Mio par token — environ huit
fois moins — et laisse TOUTE l'attention et tout le dense sur le GPU.

Ce module choisit les blocs dont les experts partent en RAM. Il ne décide de rien quand la mesure
manque : sans poids d'experts relevé bloc par bloc, `mesures_experts` rend `None` et le planificateur
retombe sur la coupe par couches. Aucun poids n'est réparti uniformément, aucune part n'est estimée.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.inference.planner.budget import (
    couches_attention,
    octets_kv_par_token_par_couche,
    octets_tampons_calcul,
    vram_effective,
)
from backend.inference.planner.entrees import MetadonneesModele, TypeCacheKV


class MesuresExperts(BaseModel):
    """Vue validée des poids relevés bloc par bloc. Construite seulement si la mesure est complète."""

    model_config = ConfigDict(frozen=True)

    octets_experts_par_bloc: tuple[int, ...]
    octets_dense_par_bloc: tuple[int, ...]
    octets_hors_blocs: int = Field(ge=0)

    @property
    def nombre_blocs(self) -> int:
        return len(self.octets_experts_par_bloc)

    @property
    def octets_socle(self) -> int:
        """Poids résident quel que soit le déport : dense de tous les blocs, plus les hors-blocs."""
        return sum(self.octets_dense_par_bloc) + self.octets_hors_blocs

    @property
    def octets_experts_totaux(self) -> int:
        return sum(self.octets_experts_par_bloc)


class PlacementExperts(BaseModel):
    """Répartition retenue des groupes d'experts entre VRAM et mémoire hôte."""

    model_config = ConfigDict(frozen=True)

    blocs_deportes: tuple[int, ...] = ()
    octets_gpu: int = Field(default=0, ge=0)
    octets_hote: int = Field(default=0, ge=0)

    @property
    def nombre_deportes(self) -> int:
        return len(self.blocs_deportes)


def mesures_experts(metadonnees: MetadonneesModele) -> MesuresExperts | None:
    """Vue exploitable des mesures par bloc, ou `None` si le modèle n'en porte pas.

    Exiger les deux mesures ensemble n'est pas de la rigueur décorative : connaître le poids total
    d'un bloc sans connaître la part de ses experts ne permet aucune décision de déport, et déduire
    l'une de l'autre par un ratio serait précisément l'estimation que la v2 supprime.
    """
    totaux = metadonnees.octets_par_bloc
    experts = metadonnees.octets_experts_par_bloc
    if not totaux or not experts or len(totaux) != len(experts):
        return None
    if not any(experts):
        return None
    return MesuresExperts(
        octets_experts_par_bloc=experts,
        octets_dense_par_bloc=tuple(total - part for total, part in zip(totaux, experts)),
        octets_hors_blocs=metadonnees.octets_hors_blocs or 0,
    )


def budget_experts_octets(
    metadonnees: MetadonneesModele,
    mesures: MesuresExperts,
    *,
    contexte: int,
    batch: int,
    type_kv: TypeCacheKV,
    flash_attention: bool,
    vram_disponible_octets: int,
    ratio_fragmentation: float,
) -> float:
    """VRAM restant aux experts une fois le socle, le cache KV et les tampons provisionnés.

    Le socle et le cache sont comptés sur la TOTALITÉ des blocs : c'est le principe même de la
    stratégie, aucune couche ne quitte le GPU. Le cache KV n'est facturé que sur les couches qui en
    portent un — sur le modèle mesuré, 10 sur 40.
    """
    budget = vram_effective(vram_disponible_octets, ratio_fragmentation)
    budget -= octets_tampons_calcul(metadonnees, contexte, batch, flash_attention)
    budget -= mesures.octets_socle
    porteuses = couches_attention(metadonnees, metadonnees.nombre_couches)
    budget -= porteuses * contexte * octets_kv_par_token_par_couche(metadonnees, type_kv)
    return budget


def placer_experts(
    mesures: MesuresExperts,
    *,
    budget_octets: float,
    plafond_residents: int,
) -> PlacementExperts:
    """Garde en VRAM le plus de groupes d'experts possible, en déportant les plus lourds d'abord.

    Tous les groupes ont le même ratio « trafic hôte par octet libéré » — le routeur en lit 8 sur 256
    quel que soit le bloc. Déporter les plus gros minimise donc le NOMBRE de blocs touchés, donc le
    trafic total : mesuré, 364 Mio sur les blocs 0-4 contre 330 Mio ensuite.

    `plafond_residents` vient d'un plan qui a échoué : une dégradation ne peut jamais remettre des
    experts en VRAM. La boucle est bornée par le nombre de blocs et s'arrête au premier qui ne tient
    plus, l'ordre étant croissant.
    """
    residents: set[int] = set()
    engage = 0
    for index in _blocs_du_plus_leger_au_plus_lourd(mesures):
        poids = mesures.octets_experts_par_bloc[index]
        if len(residents) >= plafond_residents or engage + poids > budget_octets:
            break
        residents.add(index)
        engage += poids
    deportes = tuple(index for index in range(mesures.nombre_blocs) if index not in residents)
    return PlacementExperts(
        blocs_deportes=deportes,
        octets_gpu=engage,
        octets_hote=mesures.octets_experts_totaux - engage,
    )


def _blocs_du_plus_leger_au_plus_lourd(mesures: MesuresExperts) -> tuple[int, ...]:
    """Index des blocs triés par poids d'experts croissant, l'index départageant les égalités.

    Trier par poids croissant pour REMPLIR la VRAM revient à déporter les plus lourds ; l'index en
    second critère rend le plan reproductible d'une planification à l'autre, ce qui est nécessaire
    pour que deux plans successifs soient comparables.
    """
    poids = mesures.octets_experts_par_bloc
    return tuple(sorted(range(len(poids)), key=lambda index: (poids[index], index)))


def justification_deport(metadonnees: MetadonneesModele, mesures: MesuresExperts,
                         placement: PlacementExperts) -> str:
    """Phrase affichable : ce qui est déporté, et pourquoi ce n'est pas une couche entière."""
    if not placement.blocs_deportes:
        return (
            f"Les {mesures.nombre_blocs} groupes de tenseurs d'experts tiennent en VRAM : "
            "rien n'est rappelé en mémoire hôte."
        )
    # Dense par BLOC, et non le socle divisé par les blocs : les tenseurs hors blocs ne partiraient
    # avec aucune couche, les compter ici gonflerait le coût annoncé de la coupe par couches.
    dense_moyen = sum(mesures.octets_dense_par_bloc) / max(mesures.nombre_blocs, 1)
    return (
        f"{placement.nombre_deportes} groupes d'experts sur {mesures.nombre_blocs} rappelés en "
        f"mémoire hôte ({_en_gio(placement.octets_hote)} Gio), les plus lourds d'abord. "
        f"{_routage(metadonnees)} : ces tenseurs pèsent {_part_pourcent(mesures)} % du modèle mais "
        f"une fraction seulement est lue par token. Sortir autant de VRAM en couches entières aurait "
        f"aussi renvoyé au CPU {_en_mo(dense_moyen)} Mo par couche d'attention et de dense, eux lus "
        "intégralement à chaque token."
    )


def _routage(metadonnees: MetadonneesModele) -> str:
    """Décrit le routage tel que déclaré, ou dit qu'il ne l'est pas — sans valeur de repli."""
    actifs = metadonnees.nombre_experts_actifs
    total = metadonnees.nombre_experts
    if actifs is None or total is None:
        return "Le modèle ne déclare pas son routage"
    return f"{actifs} experts sur {total} sont routés par token"


def _part_pourcent(mesures: MesuresExperts) -> int:
    total = mesures.octets_experts_totaux + mesures.octets_socle
    return int(round(100 * mesures.octets_experts_totaux / total)) if total else 0


def _en_gio(octets: float) -> float:
    return round(octets / (1024**3), 2)


def _en_mo(octets: float) -> int:
    return int(octets / (1024 * 1024))
