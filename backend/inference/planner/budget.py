"""Arithmétique mémoire du planificateur — la seule source de vérité des chiffres.

Règle fondatrice, née du défaut central de la v1 : **aucune constante magique**. Le poids d'une
couche se calcule (taille réelle du fichier / nombre réel de couches), le coût du cache KV se
calcule (dimensions d'attention × contexte × format du cache), les tampons se calculent (dimensions
du bloc transformer × batch). Rien n'est supposé.

Les seules constantes de ce module sont des **faits de format ou d'architecture** :
- la taille d'un élément f32 (4 octets) ;
- le nombre de tenseurs intermédiaires vivants dans le graphe d'un bloc transformer ;
- le pas d'alignement du contexte et du batch.

Aucun appel système ici : tout est fonction pure des entrées.
"""

from __future__ import annotations

import math

from backend.inference.planner.entrees import MetadonneesModele, TypeCacheKV
from backend.inference.planner.plan import OCTETS_PAR_ELEMENT_KV, BudgetMemoire, PosteMemoire

# Les activations circulent en f32 dans le graphe de calcul de ggml.
OCTETS_ACTIVATION = 4

# Tenseurs simultanément vivants dans le graphe d'un bloc, en dimension d'embedding : le résiduel,
# sa normalisation, Q, K, V, et la sortie de l'attention.
NB_TENSEURS_ATTENTION = 6

# Tenseurs vivants en dimension FFN : la porte, la montée, et le produit avant descente.
NB_TENSEURS_FFN = 3

# Contexte minimal en dessous duquel un modèle de conversation ne sert plus à rien. C'est une
# décision produit, pas une estimation matérielle — d'où sa présence ici, nommée et unique.
CONTEXTE_PLANCHER = 2048

# Le contexte est aligné pour rester lisible et pour coller à la granularité des blocs KV de
# llama.cpp ; le batch l'est sur la taille d'un micro-batch usuel.
PAS_CONTEXTE = 256
PAS_BATCH = 64
BATCH_PLANCHER = 64

# Défaut amont de `n_batch` dans llama.cpp, repris tel quel faute de mesure contraire.
BATCH_DEFAUT = 2048

# vLLM refuse une préallocation trop proche de 1.0 : le processus a besoin de VRAM hors pool.
PLAFOND_UTILISATION_VLLM = 0.95


def poids_par_couche_octets(metadonnees: MetadonneesModele) -> float:
    """Poids moyen d'une couche = taille réelle du fichier / nombre réel de couches.

    Le fichier contient aussi les tenseurs hors bloc (embeddings, tête de sortie) : les répartir
    uniformément sur les couches surestime légèrement chaque couche, ce qui va dans le sens de la
    prudence et évite de les oublier. La v1 supposait 150 Mo/couche ; ce calcul donne 436 Mo sur
    Qwen3.6-35B-A3B IQ4_XS, soit près de trois fois plus.
    """
    return metadonnees.taille_octets / metadonnees.nombre_couches


def dimension_tete(metadonnees: MetadonneesModele) -> int:
    """Dimension d'une tête d'attention : lue si déclarée, dérivée seulement à défaut.

    La convention `embedding / têtes` est fausse sur plusieurs architectures récentes (Qwen3
    déclare un `head_dim` indépendant) : la dérivation est un dernier recours, pas un défaut.
    """
    if metadonnees.dimension_tete is not None:
        return metadonnees.dimension_tete
    return max(1, metadonnees.dimension_embedding // metadonnees.nombre_tetes_attention)


def octets_kv_par_token_par_couche(metadonnees: MetadonneesModele, type_kv: TypeCacheKV) -> float:
    """Coût d'un token de contexte, pour une couche : clés + valeurs sur les têtes KV."""
    largeur_kv = dimension_tete(metadonnees) * metadonnees.nombre_tetes_kv
    return 2 * largeur_kv * OCTETS_PAR_ELEMENT_KV[type_kv]


def octets_tampons_calcul(
    metadonnees: MetadonneesModele,
    contexte: int,
    batch: int,
    flash_attention: bool,
) -> int:
    """Tampons de calcul GPU : activations du graphe, scores d'attention, logits de sortie.

    Sans flash attention, la matrice de scores `têtes × batch × contexte` est matérialisée et
    domine tout le reste — c'est le poste qui explose quand on allonge le contexte.
    """
    largeur_bloc = (
        NB_TENSEURS_ATTENTION * metadonnees.dimension_embedding + NB_TENSEURS_FFN * metadonnees.dimension_ffn
    )
    activations = batch * largeur_bloc * OCTETS_ACTIVATION
    scores = 0 if flash_attention else batch * metadonnees.nombre_tetes_attention * contexte * OCTETS_ACTIVATION
    logits = metadonnees.taille_vocabulaire * OCTETS_ACTIVATION
    return int(activations + scores + logits)


def vram_effective(vram_disponible_octets: int, ratio_fragmentation: float) -> float:
    """VRAM réellement allouable une fois la fragmentation de l'allocateur CUDA provisionnée."""
    return vram_disponible_octets / (1.0 + ratio_fragmentation)


def couches_gpu_maximales(
    metadonnees: MetadonneesModele,
    *,
    contexte: int,
    batch: int,
    type_kv: TypeCacheKV,
    flash_attention: bool,
    vram_disponible_octets: int,
    ratio_fragmentation: float,
) -> int:
    """Nombre maximal de couches qui tiennent, contexte et tampons déjà déduits.

    Forme close : chaque couche coûte son poids **plus** son cache KV sur toute la longueur du
    contexte. Ignorer le second terme est ce qui faisait déduire à la v1 64 couches sur GPU pour un
    modèle qui en compte 41.
    """
    budget = vram_effective(vram_disponible_octets, ratio_fragmentation)
    budget -= octets_tampons_calcul(metadonnees, contexte, batch, flash_attention)
    if budget <= 0:
        return 0
    cout_couche = poids_par_couche_octets(metadonnees) + contexte * octets_kv_par_token_par_couche(metadonnees, type_kv)
    return max(0, min(metadonnees.nombre_couches, int(budget // cout_couche)))


def contexte_maximal(
    metadonnees: MetadonneesModele,
    *,
    couches_gpu: int,
    batch: int,
    type_kv: TypeCacheKV,
    flash_attention: bool,
    vram_disponible_octets: int,
    ratio_fragmentation: float,
) -> int:
    """Contexte maximal tenable pour un nombre de couches GPU donné, aligné sur `PAS_CONTEXTE`.

    Sans couche sur GPU, le cache KV vit en RAM : seul le plafond d'entraînement s'applique ici, la
    contrainte RAM étant vérifiée séparément.
    """
    if couches_gpu <= 0:
        return metadonnees.contexte_entrainement_max
    budget = vram_effective(vram_disponible_octets, ratio_fragmentation)
    # Tampons estimés au plafond d'entraînement : sans flash attention ils dépendent du contexte,
    # et surprovisionner ici ne peut que rendre le plan plus prudent.
    budget -= octets_tampons_calcul(metadonnees, metadonnees.contexte_entrainement_max, batch, flash_attention)
    budget -= couches_gpu * poids_par_couche_octets(metadonnees)
    if budget <= 0:
        return 0
    tokens = budget / (couches_gpu * octets_kv_par_token_par_couche(metadonnees, type_kv))
    return aligner(int(tokens), PAS_CONTEXTE)


def aligner(valeur: int, pas: int) -> int:
    """Arrondit à l'inférieur sur un multiple de `pas`, sans jamais rendre zéro pour une valeur > 0."""
    if valeur < pas:
        return valeur
    return (valeur // pas) * pas


def besoin_ram_octets(
    metadonnees: MetadonneesModele,
    *,
    couches_cpu: int,
    contexte: int,
    type_kv: TypeCacheKV,
) -> int:
    """RAM hôte requise : poids des couches restées côté CPU et leur cache KV."""
    poids = couches_cpu * poids_par_couche_octets(metadonnees)
    cache = couches_cpu * contexte * octets_kv_par_token_par_couche(metadonnees, type_kv)
    return int(poids + cache)


def construire_budget(
    metadonnees: MetadonneesModele,
    *,
    couches_gpu: int,
    contexte: int,
    batch: int,
    type_kv: TypeCacheKV,
    flash_attention: bool,
    vram_disponible_octets: int,
    ram_disponible_octets: int,
    ratio_fragmentation: float,
) -> BudgetMemoire:
    """Décomposition chiffrée et justifiée de la mémoire engagée par le plan, VRAM et RAM."""
    return BudgetMemoire(
        vram_disponible_octets=vram_disponible_octets,
        postes=postes_vram(
            metadonnees,
            couches_gpu=couches_gpu,
            contexte=contexte,
            batch=batch,
            type_kv=type_kv,
            flash_attention=flash_attention,
            ratio_fragmentation=ratio_fragmentation,
        ),
        ram_requise_octets=besoin_ram_octets(
            metadonnees,
            couches_cpu=metadonnees.nombre_couches - couches_gpu,
            contexte=contexte,
            type_kv=type_kv,
        ),
        ram_disponible_octets=ram_disponible_octets,
    )


def postes_vram(
    metadonnees: MetadonneesModele,
    *,
    couches_gpu: int,
    contexte: int,
    batch: int,
    type_kv: TypeCacheKV,
    flash_attention: bool,
    ratio_fragmentation: float,
) -> tuple[PosteMemoire, ...]:
    """Les quatre postes de VRAM, chacun chiffré et justifié séparément."""
    poids = int(couches_gpu * poids_par_couche_octets(metadonnees))
    cache = int(couches_gpu * contexte * octets_kv_par_token_par_couche(metadonnees, type_kv))
    tampons = octets_tampons_calcul(metadonnees, contexte, batch, flash_attention)
    fragmentation = int((poids + cache + tampons) * ratio_fragmentation)
    return (
        _poste_poids(metadonnees, couches_gpu, poids),
        _poste_cache(metadonnees, couches_gpu, contexte, type_kv, cache),
        _poste_tampons(metadonnees, batch, flash_attention, tampons),
        _poste_fragmentation(ratio_fragmentation, fragmentation),
    )


def _poste_poids(metadonnees: MetadonneesModele, couches_gpu: int, octets: int) -> PosteMemoire:
    """Poste des poids : la justification affiche le calcul, pas seulement son résultat."""
    return PosteMemoire(
        libelle="Poids des couches sur GPU",
        octets=octets,
        justification=(
            f"{couches_gpu} couches x {_en_mo(poids_par_couche_octets(metadonnees))} Mo, "
            f"soit la taille du fichier divisée par ses {metadonnees.nombre_couches} couches réelles."
        ),
    )


def _poste_cache(metadonnees: MetadonneesModele, couches_gpu: int, contexte: int,
                 type_kv: TypeCacheKV, octets: int) -> PosteMemoire:
    """Poste du cache KV : c'est lui qui rend le contexte coûteux, il doit être chiffré à part."""
    return PosteMemoire(
        libelle="Cache KV",
        octets=octets,
        justification=(
            f"{contexte} tokens x {couches_gpu} couches x "
            f"{octets_kv_par_token_par_couche(metadonnees, type_kv):.0f} o/token/couche en {type_kv.value}."
        ),
    )


def _poste_tampons(metadonnees: MetadonneesModele, batch: int, flash_attention: bool, octets: int) -> PosteMemoire:
    """Poste des tampons de calcul, dominé par la matrice de scores quand flash attention est absente."""
    complement = (
        "." if flash_attention else ", plus la matrice de scores d'attention (flash attention désactivée)."
    )
    return PosteMemoire(
        libelle="Tampons de calcul",
        octets=octets,
        justification=(
            f"Activations du graphe pour un batch de {batch}, logits sur "
            f"{metadonnees.taille_vocabulaire} tokens{complement}"
        ),
    )


def _poste_fragmentation(ratio: float, octets: int) -> PosteMemoire:
    """Seul poste non dérivé d'une grandeur du modèle : il est signalé comme tel."""
    return PosteMemoire(
        libelle="Réserve de fragmentation",
        octets=octets,
        justification=(
            f"{ratio:.0%} du total alloué, pour la granularité de l'allocateur CUDA. "
            "Valeur par défaut prudente, non mesurée sur cette machine."
        ),
    )


def utilisation_memoire_gpu(budget: BudgetMemoire, vram_totale_octets: int) -> float:
    """Fraction de VRAM que vLLM doit préallouer, déduite du besoin réel du plan.

    La v1 tâtonnait par paliers (0.72 puis 0.78 puis 0.80) après chaque échec ; ici la valeur sort
    du budget calculé et n'est que plafonnée par ce que le processus vLLM exige hors pool.
    """
    if vram_totale_octets <= 0:
        return PLAFOND_UTILISATION_VLLM
    brute = budget.vram_requise_octets / vram_totale_octets
    return min(PLAFOND_UTILISATION_VLLM, math.ceil(brute * 100) / 100)


def _en_mo(octets: float) -> int:
    """Conversion en mébioctets pour les justifications lisibles."""
    return int(octets / (1024 * 1024))
