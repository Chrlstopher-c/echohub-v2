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
from backend.inference.planner.plan import OCTETS_PAR_ELEMENT_KV, BudgetMemoire

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


def poids_cumule_gpu_octets(metadonnees: MetadonneesModele, couches_gpu: int) -> float:
    """Poids résident en VRAM pour `couches_gpu` blocs : mesure par bloc si elle existe, moyenne sinon.

    La moyenne fichier/couches répartit implicitement les tenseurs hors blocs sur les couches. Dès
    qu'on dispose de la mesure par bloc, cette compensation disparaît : les tenseurs hors blocs sont
    alors facturés explicitement dès la première couche déléguée, llama.cpp y plaçant la tête de
    sortie. Mesuré sur le 0.5B, `token_embd` reste côté hôte — le compter ici sur-provisionne de sa
    taille, ce qui est le sens prudent.
    """
    if couches_gpu <= 0:
        return 0.0
    blocs = metadonnees.octets_par_bloc
    if not blocs:
        return couches_gpu * poids_par_couche_octets(metadonnees)
    retenus = min(couches_gpu, len(blocs))
    return float(sum(blocs[:retenus]) + (metadonnees.octets_hors_blocs or 0))


def couches_attention(metadonnees: MetadonneesModele, couches: int) -> int:
    """Couches portant un cache KV parmi les `couches` premiers blocs.

    Mesuré sur les deux modèles présents : `full_attention_interval` vaut 4 et seuls les blocs
    3, 7, 11 … 39 portent un `attn_q.weight`, soit 10 couches sur 40. Facturer le cache KV sur les
    40 blocs inventait 1,9 Gio de VRAM à 32k et 3,3 Gio à 57k — l'essentiel de la VRAM constatée
    inutilisée. Clé absente = toutes les couches portent un cache, sans substitution.
    """
    intervalle = metadonnees.intervalle_attention_pleine
    retenues = max(0, couches)
    if intervalle is None or intervalle <= 1:
        return retenues
    return retenues // intervalle


def largeur_activation_ffn(metadonnees: MetadonneesModele) -> int | None:
    """Largeur FFN vive dans le graphe d'un bloc, en éléments — `None` si rien ne la déclare.

    Sur un MoE, ce n'est pas la largeur d'un expert : `nombre_experts_actifs` experts sont routés
    ensemble à chaque token, plus l'expert partagé. Prendre `expert_feed_forward_length` telle quelle
    sous-dimensionnerait le tampon d'un facteur 8 sur le modèle mesuré. On retient la plus grande des
    largeurs déclarées : le tampon doit tenir le bloc le plus large du graphe, et rien ne dit qu'un
    modèle ne mélange pas blocs denses et blocs à experts.
    """
    largeurs = [
        valeur
        for valeur in (_largeur_ffn_experts(metadonnees), metadonnees.dimension_ffn)
        if valeur is not None
    ]
    return max(largeurs) if largeurs else None


def _largeur_ffn_experts(metadonnees: MetadonneesModele) -> int | None:
    """Largeur cumulée des experts vivants d'un bloc, ou `None` si le modèle n'en déclare pas.

    L'expert partagé absent est lu comme « aucun expert partagé déclaré » — c'est ainsi que
    llama.cpp lui-même traite l'absence de la clé, pas une valeur substituée.
    """
    largeur_expert = metadonnees.dimension_ffn_expert
    actifs = metadonnees.nombre_experts_actifs
    if largeur_expert is None or actifs is None:
        return None
    return largeur_expert * actifs + (metadonnees.dimension_ffn_expert_partage or 0)


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

    Largeur FFN non déclarée : le terme d'activations est omis plutôt qu'estimé, et
    `avertissements_metadonnees` le signale dans le plan. Un tampon inventé se verrait moins qu'un
    tampon manquant, qui produit un échec de chargement franc et une dégradation.
    """
    largeur_ffn = largeur_activation_ffn(metadonnees) or 0
    largeur_bloc = NB_TENSEURS_ATTENTION * metadonnees.dimension_embedding + NB_TENSEURS_FFN * largeur_ffn
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

    La forme close suppose un coût uniforme. Dès qu'une mesure la contredit — poids relevé bloc par
    bloc, ou architecture hybride où une couche sur quatre seulement porte un cache KV — on accumule
    bloc par bloc au lieu de diviser.
    """
    budget = vram_effective(vram_disponible_octets, ratio_fragmentation)
    budget -= octets_tampons_calcul(metadonnees, contexte, batch, flash_attention)
    if budget <= 0:
        return 0
    if metadonnees.octets_par_bloc or metadonnees.intervalle_attention_pleine is not None:
        return _couches_tenables_par_accumulation(metadonnees, budget, contexte=contexte, type_kv=type_kv)
    cout_couche = poids_par_couche_octets(metadonnees) + contexte * octets_kv_par_token_par_couche(metadonnees, type_kv)
    return max(0, min(metadonnees.nombre_couches, int(budget // cout_couche)))


def _couches_tenables_par_accumulation(
    metadonnees: MetadonneesModele,
    budget: float,
    *,
    contexte: int,
    type_kv: TypeCacheKV,
) -> int:
    """Plus grand nombre de blocs dont le coût cumulé tient dans `budget`.

    Boucle bornée par le nombre de blocs du modèle, jamais par une condition dynamique : elle
    s'arrête au premier cumul qui dépasse, les coûts étant croissants par construction.
    """
    kv_par_token = octets_kv_par_token_par_couche(metadonnees, type_kv)
    for couches in range(1, metadonnees.nombre_couches + 1):
        cumul = poids_cumule_gpu_octets(metadonnees, couches)
        cumul += couches_attention(metadonnees, couches) * contexte * kv_par_token
        if cumul > budget:
            return couches - 1
    return metadonnees.nombre_couches


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
    budget -= poids_cumule_gpu_octets(metadonnees, couches_gpu)
    if budget <= 0:
        return 0
    porteuses = couches_attention(metadonnees, couches_gpu)
    if porteuses <= 0:
        # Aucune des couches déléguées ne porte de cache KV : le contexte ne coûte plus de VRAM, il
        # n'est plus borné que par l'entraînement du modèle.
        return metadonnees.contexte_entrainement_max
    tokens = budget / (porteuses * octets_kv_par_token_par_couche(metadonnees, type_kv))
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
    octets_experts_hote: int = 0,
) -> int:
    """RAM hôte requise : couches restées côté CPU, leur cache KV, et les experts rappelés en RAM.

    `octets_experts_hote` couvre le cas où toutes les couches sont sur GPU et où seuls des groupes de
    tenseurs d'experts vivent côté hôte : ces octets ne sont portés par aucune couche CPU.
    """
    poids = couches_cpu * poids_par_couche_octets(metadonnees)
    total = metadonnees.nombre_couches
    porteuses = couches_attention(metadonnees, total) - couches_attention(metadonnees, total - couches_cpu)
    cache = porteuses * contexte * octets_kv_par_token_par_couche(metadonnees, type_kv)
    return int(poids + cache + octets_experts_hote)


def avertissements_metadonnees(metadonnees: MetadonneesModele) -> tuple[str, ...]:
    """Ce que le budget ne sait PAS provisionner, faute de mesure — dit au lieu d'être comblé."""
    lignes: list[str] = []
    if largeur_activation_ffn(metadonnees) is None:
        lignes.append(
            "Largeur du bloc FFN non déclarée par le modèle : le poste des tampons de calcul est "
            "sous-provisionné de ce terme. Un échec de chargement fera dégrader le plan."
        )
    if metadonnees.intervalle_attention_pleine is not None:
        lignes.append(
            f"Architecture hybride : une couche sur {metadonnees.intervalle_attention_pleine} porte "
            "un cache KV, les autres portent un état récurrent dont la taille n'est pas lue "
            "(clés `ssm.*`). Ce poste, mesuré à 62,8 Mio sur le 35B, n'est pas provisionné."
        )
    return tuple(lignes)


def utilisation_memoire_gpu(budget: BudgetMemoire, vram_totale_octets: int) -> float:
    """Fraction de VRAM que vLLM doit préallouer, déduite du besoin réel du plan.

    La v1 tâtonnait par paliers (0.72 puis 0.78 puis 0.80) après chaque échec ; ici la valeur sort
    du budget calculé et n'est que plafonnée par ce que le processus vLLM exige hors pool.
    """
    if vram_totale_octets <= 0:
        return PLAFOND_UTILISATION_VLLM
    brute = budget.vram_requise_octets / vram_totale_octets
    return min(PLAFOND_UTILISATION_VLLM, math.ceil(brute * 100) / 100)
