"""Tables du format GGUF/GGML — transcription d'un format externe, sans logique métier.

Ces valeurs sont relevées dans `ggml.h` et `llama.h`, ce ne sont pas des constantes de réglage.
Elles sont isolées ici pour qu'on voie d'un coup d'œil ce qui vient du format et ce qui vient de
nous.

Règle qui gouverne tout le module : **une entrée absente reste absente**. `traits_ggml` et
`nom_ftype` retournent `None` plutôt qu'un défaut. La v1 faisait l'inverse — `factors.get(variante,
0.55)` — et une quantification non reconnue passait silencieusement pour un Q4_K_M, avec une
estimation de VRAM fausse en bout de chaîne.
"""

from __future__ import annotations

import struct
from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field


class TypeValeurGGUF(IntEnum):
    """Types admis pour une valeur de métadonnée GGUF (`gguf_metadata_value_type`)."""

    UINT8 = 0
    INT8 = 1
    UINT16 = 2
    INT16 = 3
    UINT32 = 4
    INT32 = 5
    FLOAT32 = 6
    BOOL = 7
    STRING = 8
    ARRAY = 9
    UINT64 = 10
    INT64 = 11
    FLOAT64 = 12


# Format `struct` de chaque scalaire. La taille en octets s'en déduit par `struct.calcsize` : une
# seule table, donc aucune possibilité qu'une taille et un format divergent.
FORMATS_SCALAIRES: dict[TypeValeurGGUF, str] = {
    TypeValeurGGUF.UINT8: "<B",
    TypeValeurGGUF.INT8: "<b",
    TypeValeurGGUF.UINT16: "<H",
    TypeValeurGGUF.INT16: "<h",
    TypeValeurGGUF.UINT32: "<I",
    TypeValeurGGUF.INT32: "<i",
    TypeValeurGGUF.FLOAT32: "<f",
    TypeValeurGGUF.BOOL: "<?",
    TypeValeurGGUF.UINT64: "<Q",
    TypeValeurGGUF.INT64: "<q",
    TypeValeurGGUF.FLOAT64: "<d",
}


def taille_scalaire(type_valeur: TypeValeurGGUF) -> int | None:
    """Octets occupés par un scalaire de ce type, ou `None` si le type n'est pas scalaire."""
    format_struct = FORMATS_SCALAIRES.get(type_valeur)
    return struct.calcsize(format_struct) if format_struct else None


class TraitsGGML(BaseModel):
    """Empreinte mémoire d'un type de tenseur ggml : un bloc de N éléments occupe M octets.

    C'est ce qui permet de calculer le poids réel d'une couche au lieu de le supposer.
    """

    model_config = ConfigDict(frozen=True)

    nom: str
    elements_par_bloc: int = Field(gt=0)
    octets_par_bloc: int = Field(gt=0)

    def octets(self, nb_elements: int) -> int:
        """Octets occupés par `nb_elements` éléments.

        Division plafonnée : un tenseur GGUF bien formé a toujours un nombre d'éléments multiple
        de `elements_par_bloc`, mais un fichier corrompu ne doit pas faire échouer le calcul de
        taille — l'incohérence est signalée par `coherence`, pas par une exception ici.
        """
        return -(-nb_elements // self.elements_par_bloc) * self.octets_par_bloc


def _traits(nom: str, elements_par_bloc: int, octets_par_bloc: int) -> TraitsGGML:
    return TraitsGGML(nom=nom, elements_par_bloc=elements_par_bloc, octets_par_bloc=octets_par_bloc)


# Identifiants `ggml_type`. Les valeurs retirées en amont (Q4_2, Q4_3, les variantes Q4_0_M_N) sont
# volontairement absentes : un fichier qui les utilise n'est plus chargeable par llama.cpp, et le
# signaler vaut mieux que le mesurer.
TRAITS_GGML: dict[int, TraitsGGML] = {
    0: _traits("F32", 1, 4),
    1: _traits("F16", 1, 2),
    2: _traits("Q4_0", 32, 18),
    3: _traits("Q4_1", 32, 20),
    6: _traits("Q5_0", 32, 22),
    7: _traits("Q5_1", 32, 24),
    8: _traits("Q8_0", 32, 34),
    9: _traits("Q8_1", 32, 36),
    10: _traits("Q2_K", 256, 84),
    11: _traits("Q3_K", 256, 110),
    12: _traits("Q4_K", 256, 144),
    13: _traits("Q5_K", 256, 176),
    14: _traits("Q6_K", 256, 210),
    15: _traits("Q8_K", 256, 292),
    16: _traits("IQ2_XXS", 256, 66),
    17: _traits("IQ2_XS", 256, 74),
    18: _traits("IQ3_XXS", 256, 98),
    19: _traits("IQ1_S", 256, 50),
    20: _traits("IQ4_NL", 32, 18),
    21: _traits("IQ3_S", 256, 110),
    22: _traits("IQ2_S", 256, 82),
    23: _traits("IQ4_XS", 256, 136),
    24: _traits("I8", 1, 1),
    25: _traits("I16", 1, 2),
    26: _traits("I32", 1, 4),
    27: _traits("I64", 1, 8),
    28: _traits("F64", 1, 8),
    29: _traits("IQ1_M", 256, 56),
    30: _traits("BF16", 1, 2),
    34: _traits("TQ1_0", 256, 54),
    35: _traits("TQ2_0", 256, 66),
    39: _traits("MXFP4", 32, 17),
}


def traits_ggml(identifiant: int) -> TraitsGGML | None:
    """Traits d'un type de tenseur, ou `None` si l'identifiant est inconnu de cette table."""
    return TRAITS_GGML.get(identifiant)


# `general.file_type` — enum `llama_ftype`. C'est la quantification **déclarée** à l'export ; elle
# ne dit rien des tenseurs réellement présents. Les identifiants dont la correspondance n'est pas
# établie de façon certaine sont omis : `nom_ftype` rend alors `None`, et le calcul retombe sur la
# quantification mesurée dans les descripteurs de tenseurs, qui est de toute façon l'autorité.
NOMS_FTYPE: dict[int, str] = {
    0: "F32",
    1: "F16",
    2: "Q4_0",
    3: "Q4_1",
    7: "Q8_0",
    8: "Q5_0",
    9: "Q5_1",
    10: "Q2_K",
    11: "Q3_K_S",
    12: "Q3_K_M",
    13: "Q3_K_L",
    14: "Q4_K_S",
    15: "Q4_K_M",
    16: "Q5_K_S",
    17: "Q5_K_M",
    18: "Q6_K",
    19: "IQ2_XXS",
    20: "IQ2_XS",
    21: "Q2_K_S",
    22: "IQ3_XS",
    23: "IQ3_XXS",
    24: "IQ1_S",
    25: "IQ4_NL",
    26: "IQ3_S",
    27: "IQ3_M",
    28: "IQ2_S",
    29: "IQ2_M",
    30: "IQ4_XS",
    31: "IQ1_M",
    32: "BF16",
    36: "TQ1_0",
    37: "TQ2_0",
}


def nom_ftype(identifiant: int) -> str | None:
    """Nom lisible d'un `general.file_type`, ou `None` si l'identifiant n'est pas répertorié."""
    return NOMS_FTYPE.get(identifiant)


# --- Nommage des tenseurs -----------------------------------------------------------------------
#
# Ces marqueurs sont eux aussi une transcription : llama.cpp nomme ses tenseurs selon un gabarit
# fixe, et c'est le NOM qui dit à quoi sert un poids. Reconnaître un nom n'estime rien — au pire un
# gabarit inconnu n'est pas reconnu, et la mesure correspondante reste vide au lieu d'être fausse.

# Experts ROUTÉS d'un MoE : `blk.N.ffn_{gate,up,down}_exps.weight`. 120 relevés sur les 40 blocs du
# Qwen3.6-35B-A3B, soit 90,9 % du fichier. Ce sont les seuls poids dont la lecture dépend du routage
# (8 experts sur 256 par token) : eux seuls peuvent être déportés en mémoire hôte sans que leur
# trafic soit payé intégralement à chaque token.
MARQUEURS_EXPERTS = ("_exps.", "_exps_")

# Expert PARTAGÉ : `blk.N.ffn_{gate,up,down}_shexp.weight`, évalué à chaque token quel que soit le
# routage. Son nom ne contient pas `_exps`, donc les marqueurs ci-dessus ne l'attrapent pas — c'est
# exactement la distinction voulue, et un test la fige.
MARQUEUR_EXPERT_PARTAGE = "_shexp"

# Projection des requêtes d'attention. `attn_q.` est la forme relevée sur les deux modèles de la
# machine, `attn_qkv.` la forme fusionnée d'autres familles. Aucune reconnue ⇒ aucun bloc d'attention
# relevé, ce qui se lit « non mesuré » et jamais « ce modèle n'a pas d'attention ».
MARQUEURS_ATTENTION = ("attn_q.", "attn_qkv.")


def est_tenseur_expert(nom_tenseur: str) -> bool:
    """Vrai pour un tenseur d'experts ROUTÉS, faux pour l'expert partagé et le reste du bloc."""
    return any(marqueur in nom_tenseur for marqueur in MARQUEURS_EXPERTS)


def porte_attention(nom_tenseur: str) -> bool:
    """Vrai si le tenseur est une projection de requêtes : son bloc porte donc une attention."""
    return any(marqueur in nom_tenseur for marqueur in MARQUEURS_ATTENTION)
