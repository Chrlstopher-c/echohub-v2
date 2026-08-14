"""Fabrique d'en-têtes GGUF minuscules — en mémoire ou sur disque, sans GPU ni fichier de plusieurs Go.

Le modèle de référence de ces tests pèse quelques dizaines de kilo-octets, mais sa **structure** est
celle relevée sur HauhauCS/Qwen3.6-35B-A3B : `feed_forward_length` absente et
`expert_feed_forward_length` présente, experts routés `ffn_*_exps` d'un côté et expert partagé
`ffn_*_shexp` de l'autre, une couche d'attention seulement tous les `full_attention_interval` blocs.
Ce sont ces trois traits, et non les tailles, qui ont bloqué le modèle réel.

Les chiffres sont volontairement petits et exacts : chaque poids attendu par un test se recalcule à
la main depuis les dimensions déclarées ici, sans facteur ni arrondi.
"""

from __future__ import annotations

import struct
from pathlib import Path

from backend.models.gguf_reader import (
    ALIGNEMENT_PAR_DEFAUT,
    MAGIC_GGUF,
    EnTeteGGUF,
    InfoTenseur,
    ValeurGGUF,
)
from backend.models.gguf_types import TypeValeurGGUF, traits_ggml

VERSION_ECRITE = 3
TYPE_F32 = 0  # 4 octets par élément : tout poids attendu se lit « nb_elements × 4 ».
OCTETS_F32 = 4

ARCHITECTURE_MOE = "qwen35moe"
ARCHITECTURE_DENSE = "qwen35"

NB_BLOCS = 4
NB_EXPERTS = 8
NB_EXPERTS_ACTIFS = 2
LARGEUR_EXPERT = 16
LARGEUR_PARTAGEE = 8
INTERVALLE_ATTENTION = 2
BLOCS_ATTENTION = (1, 3)

# Formes des tenseurs d'un bloc. La dernière dimension d'un tenseur d'experts porte leur cardinal :
# `coherence` s'en sert pour attraper un fichier construit pour un autre nombre d'experts.
FORME_EXPERT = (LARGEUR_EXPERT, 32, NB_EXPERTS)
FORME_PARTAGE = (LARGEUR_PARTAGEE, 32)
FORME_NORME = (32,)
FORME_ATTENTION = (32, 32)

OCTETS_EXPERTS_PAR_BLOC = 3 * LARGEUR_EXPERT * 32 * NB_EXPERTS * OCTETS_F32  # 49 152
OCTETS_DENSE_PAR_BLOC = (LARGEUR_PARTAGEE * 32 + 32) * OCTETS_F32  # 1 152
OCTETS_ATTENTION_PAR_BLOC = 32 * 32 * OCTETS_F32  # 4 096
OCTETS_HORS_BLOCS = 2 * 32 * 100 * OCTETS_F32  # 25 600


def _chaine_encodee(valeur: str) -> bytes:
    """Chaîne GGUF : longueur sur 8 octets, puis les octets UTF-8."""
    brut = valeur.encode("utf-8")
    return struct.pack("<Q", len(brut)) + brut


def _valeur_encodee(valeur: ValeurGGUF) -> bytes:
    """Valeur de métadonnée précédée de son marqueur de type. `bool` avant `int` : c'en est un."""
    if isinstance(valeur, bool):
        return struct.pack("<I?", int(TypeValeurGGUF.BOOL), valeur)
    if isinstance(valeur, int):
        return struct.pack("<II", int(TypeValeurGGUF.UINT32), valeur)
    if isinstance(valeur, float):
        return struct.pack("<If", int(TypeValeurGGUF.FLOAT32), valeur)
    if isinstance(valeur, str):
        return struct.pack("<I", int(TypeValeurGGUF.STRING)) + _chaine_encodee(valeur)
    if not isinstance(valeur, list):
        raise TypeError(f"valeur non encodable par la fabrique : {valeur!r}")
    entiers = [element for element in valeur if isinstance(element, int)]
    if len(entiers) != len(valeur):
        raise TypeError("la fabrique n'encode que des tableaux d'entiers")
    entete = struct.pack("<IIQ", int(TypeValeurGGUF.ARRAY), int(TypeValeurGGUF.UINT32), len(entiers))
    return entete + b"".join(struct.pack("<I", element) for element in entiers)


def _descripteur_encode(tenseur: InfoTenseur, offset: int) -> bytes:
    """Descripteur de tenseur : nom, dimensions, type ggml, position dans la zone de données."""
    dimensions = b"".join(struct.pack("<Q", dimension) for dimension in tenseur.dimensions)
    return (
        _chaine_encodee(tenseur.nom)
        + struct.pack("<I", len(tenseur.dimensions))
        + dimensions
        + struct.pack("<IQ", tenseur.type_ggml, offset)
    )


def _octets_alignes(tenseur: InfoTenseur) -> int:
    """Place réellement occupée par un tenseur dans la zone de données, alignement compris."""
    traits = traits_ggml(tenseur.type_ggml)
    if traits is None:
        raise ValueError(f"type ggml {tenseur.type_ggml} absent des tables : taille inconnue")
    octets = traits.octets(tenseur.nb_elements)
    return -(-octets // ALIGNEMENT_PAR_DEFAUT) * ALIGNEMENT_PAR_DEFAUT


def ecrire_gguf(chemin: Path, cles: dict[str, ValeurGGUF], tenseurs: list[InfoTenseur]) -> Path:
    """Écrit un GGUF v3 valide : en-tête, descripteurs, puis une zone de données à zéro.

    Les offsets portés par les `InfoTenseur` sont ignorés et recalculés séquentiellement : c'est le
    fichier écrit qui fait foi, et `coherence` vérifie ensuite que les descripteurs tiennent dedans.
    """
    corps = b"".join(_chaine_encodee(cle) + _valeur_encodee(valeur) for cle, valeur in cles.items())
    descripteurs = b""
    octets_donnees = 0
    for tenseur in tenseurs:
        descripteurs += _descripteur_encode(tenseur, octets_donnees)
        octets_donnees += _octets_alignes(tenseur)

    entete = MAGIC_GGUF + struct.pack("<IQQ", VERSION_ECRITE, len(tenseurs), len(cles)) + corps + descripteurs
    rembourrage = -len(entete) % ALIGNEMENT_PAR_DEFAUT
    chemin.write_bytes(entete + b"\x00" * (rembourrage + octets_donnees))
    return chemin


def entete_en_memoire(cles: dict[str, ValeurGGUF], tenseurs: list[InfoTenseur]) -> EnTeteGGUF:
    """En-tête construit directement : `depuis_entete` est pur, il n'a jamais besoin d'octets."""
    return EnTeteGGUF(
        chemin="fabrique.gguf",
        version=VERSION_ECRITE,
        nb_tenseurs_declares=len(tenseurs),
        nb_cles_declarees=len(cles),
        cles=dict(cles),
        tenseurs=list(tenseurs),
        alignement=ALIGNEMENT_PAR_DEFAUT,
        offset_donnees=0,
        taille_fichier_octets=0,
    )


def _appliquer(cles: dict[str, ValeurGGUF], surcharges: dict[str, ValeurGGUF | None]) -> dict[str, ValeurGGUF]:
    """Applique des surcharges ; une valeur `None` RETIRE la clé — c'est ainsi qu'on rejoue une absence."""
    resultat = dict(cles)
    for cle, valeur in surcharges.items():
        if valeur is None:
            resultat.pop(cle, None)
        else:
            resultat[cle] = valeur
    return resultat


def cles_moe(surcharges: dict[str, ValeurGGUF | None] | None = None) -> dict[str, ValeurGGUF]:
    """Clés du MoE hybride de référence. `{arch}.feed_forward_length` est volontairement absente."""
    prefixe = ARCHITECTURE_MOE
    cles: dict[str, ValeurGGUF] = {
        "general.architecture": ARCHITECTURE_MOE,
        "general.name": "moe-minuscule",
        "general.file_type": 0,
        f"{prefixe}.block_count": NB_BLOCS,
        f"{prefixe}.context_length": 4096,
        f"{prefixe}.embedding_length": 32,
        f"{prefixe}.vocab_size": 128,
        f"{prefixe}.expert_count": NB_EXPERTS,
        f"{prefixe}.expert_used_count": NB_EXPERTS_ACTIFS,
        f"{prefixe}.expert_feed_forward_length": LARGEUR_EXPERT,
        f"{prefixe}.expert_shared_feed_forward_length": LARGEUR_PARTAGEE,
        f"{prefixe}.expert_gating_func": 2,
        f"{prefixe}.expert_weights_scale": 2.5,
        f"{prefixe}.expert_weights_norm": True,
        f"{prefixe}.full_attention_interval": INTERVALLE_ATTENTION,
        f"{prefixe}.attention.head_count": 4,
        f"{prefixe}.attention.head_count_kv": 1,
        f"{prefixe}.attention.key_length": 8,
        f"{prefixe}.attention.value_length": 8,
        f"{prefixe}.rope.dimension_count": 8,
        f"{prefixe}.rope.dimension_sections": [3, 3, 2, 0],
        f"{prefixe}.rope.freq_base": 10000000.0,
        f"{prefixe}.ssm.inner_size": 64,
        f"{prefixe}.ssm.state_size": 16,
        f"{prefixe}.ssm.conv_kernel": 4,
        f"{prefixe}.ssm.time_step_rank": 8,
        f"{prefixe}.ssm.group_count": 2,
    }
    return _appliquer(cles, surcharges or {})


def cles_denses(surcharges: dict[str, ValeurGGUF | None] | None = None) -> dict[str, ValeurGGUF]:
    """Modèle dense de contrôle : `feed_forward_length` présente, aucune clé MoE ni SSM."""
    prefixe = ARCHITECTURE_DENSE
    cles: dict[str, ValeurGGUF] = {
        "general.architecture": ARCHITECTURE_DENSE,
        "general.file_type": 0,
        f"{prefixe}.block_count": 2,
        f"{prefixe}.context_length": 4096,
        f"{prefixe}.embedding_length": 32,
        f"{prefixe}.feed_forward_length": 64,
        f"{prefixe}.attention.head_count": 4,
        f"{prefixe}.attention.head_count_kv": 1,
    }
    return _appliquer(cles, surcharges or {})


def _tenseur(nom: str, dimensions: tuple[int, ...], type_ggml: int = TYPE_F32) -> InfoTenseur:
    """Descripteur nu. L'offset ne sert qu'à l'écriture sur disque, qui le recalcule."""
    return InfoTenseur(nom=nom, dimensions=dimensions, type_ggml=type_ggml, offset_octets=0)


def tenseurs_moe(
    nb_blocs: int = NB_BLOCS,
    blocs_attention: tuple[int, ...] = BLOCS_ATTENTION,
) -> list[InfoTenseur]:
    """Tenseurs du MoE hybride : trois experts routés par bloc, un expert partagé, une norme.

    Seuls les blocs de `blocs_attention` portent une projection de requêtes — c'est la structure
    hybride relevée, où trois couches sur quatre n'ont pas de cache KV mais un état récurrent.
    """
    tenseurs = [_tenseur("token_embd.weight", (32, 100)), _tenseur("output.weight", (100, 32))]
    for bloc in range(nb_blocs):
        for porte in ("gate", "up", "down"):
            tenseurs.append(_tenseur(f"blk.{bloc}.ffn_{porte}_exps.weight", FORME_EXPERT))
        tenseurs.append(_tenseur(f"blk.{bloc}.ffn_gate_shexp.weight", FORME_PARTAGE))
        tenseurs.append(_tenseur(f"blk.{bloc}.ffn_norm.weight", FORME_NORME))
        if bloc in blocs_attention:
            tenseurs.append(_tenseur(f"blk.{bloc}.attn_q.weight", FORME_ATTENTION))
    return tenseurs


def tenseurs_denses(nb_blocs: int = 2) -> list[InfoTenseur]:
    """Tenseurs d'un modèle dense : aucune trace d'experts, une attention par bloc."""
    tenseurs = [_tenseur("token_embd.weight", (32, 100))]
    for bloc in range(nb_blocs):
        tenseurs.append(_tenseur(f"blk.{bloc}.ffn_gate.weight", (64, 32)))
        tenseurs.append(_tenseur(f"blk.{bloc}.attn_q.weight", FORME_ATTENTION))
    return tenseurs
