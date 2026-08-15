"""Tests du regroupement des parts GGUF et du total qu'elles couvrent.

Constaté le 2026-08-14 (`download_selection.py:32-33`) : un téléchargement annoncé « terminé »
n'avait rapporté que la part 2 sur 2 de Qwen3-Coder-30B, sans gabarit de conversation. Le
correctif (`parts_du_meme_modele`, `octets_totaux`) était écrit et poussé mais n'avait **aucune**
couverture — ce fichier comble ce trou.

Ce que ces tests protègent, dans l'ordre du risque réel :

1. **le regroupement retrouve toutes les parts d'UN modèle**, triées par rang — la seule façon
   d'obtenir un fichier avec un en-tête exploitable ;
2. **un modèle en une seule partie n'est pas touché** — `[cible]`, pas de faux positif sur un
   fichier qui n'a jamais été découpé ;
3. **deux modèles découpés du même dépôt ne se mélangent pas** — le motif capture `base` ET
   `total`, pas seulement le rang ;
4. **un nom qui ressemble à une part sans en être une** ne matche pas le motif : une extension
   différente, un nombre de chiffres différent, une absence de rang ;
5. **le total de progression couvre toutes les parts**, jamais une seule — c'est le bug réel
   du 2026-08-14, reproduit puis corrigé.
"""

from __future__ import annotations

from backend.models.discovery import FichierDepot
from backend.models.download_selection import octets_totaux, parts_du_meme_modele


def _fichier(nom: str, taille_octets: int | None = 1000) -> FichierDepot:
    return FichierDepot(nom=nom, taille_octets=taille_octets)


# ------------------------------------------------------- regroupement des parts


def test_modele_en_plusieurs_parts_est_regroupe_et_trie() -> None:
    """Les trois parts d'un modèle découpé sont retrouvées et triées par rang."""
    fichiers = [
        _fichier("qwen3-coder-30b-00003-of-00003.gguf"),
        _fichier("qwen3-coder-30b-00001-of-00003.gguf"),
        _fichier("qwen3-coder-30b-00002-of-00003.gguf"),
        _fichier("qwen3-coder-30b.md"),
    ]

    resultat = parts_du_meme_modele("qwen3-coder-30b-00002-of-00003.gguf", fichiers)

    assert resultat == [
        "qwen3-coder-30b-00001-of-00003.gguf",
        "qwen3-coder-30b-00002-of-00003.gguf",
        "qwen3-coder-30b-00003-of-00003.gguf",
    ]


def test_modele_en_une_seule_partie_n_est_pas_affecte() -> None:
    """Un GGUF qui n'a jamais été découpé rend `[cible]`, sans chercher de frère."""
    fichiers = [_fichier("qwen2.5-7b-instruct-q4_k_m.gguf"), _fichier("README.md")]

    resultat = parts_du_meme_modele("qwen2.5-7b-instruct-q4_k_m.gguf", fichiers)

    assert resultat == ["qwen2.5-7b-instruct-q4_k_m.gguf"]


def test_deux_modeles_decoupes_dans_le_meme_depot_ne_se_melangent_pas() -> None:
    """`base` et `total` font tous les deux partie de la clé de regroupement.

    Un dépôt qui publie deux quantifications découpées différemment (deux parts pour l'une, trois
    pour l'autre) ne doit jamais faire déborder les parts de l'une dans l'autre.
    """
    fichiers = [
        _fichier("modele-q4-00001-of-00002.gguf"),
        _fichier("modele-q4-00002-of-00002.gguf"),
        _fichier("modele-q8-00001-of-00003.gguf"),
        _fichier("modele-q8-00002-of-00003.gguf"),
        _fichier("modele-q8-00003-of-00003.gguf"),
    ]

    parts_q4 = parts_du_meme_modele("modele-q4-00001-of-00002.gguf", fichiers)
    parts_q8 = parts_du_meme_modele("modele-q8-00002-of-00003.gguf", fichiers)

    assert parts_q4 == ["modele-q4-00001-of-00002.gguf", "modele-q4-00002-of-00002.gguf"]
    assert parts_q8 == [
        "modele-q8-00001-of-00003.gguf",
        "modele-q8-00002-of-00003.gguf",
        "modele-q8-00003-of-00003.gguf",
    ]


def test_meme_prefixe_mais_total_different_ne_se_melange_pas() -> None:
    """Isole l'invariant `total` : deux jeux de parts au même préfixe ne se confondent pas
    seulement parce que `base` matche — il faut aussi que `total` matche.

    Contrairement au test précédent (préfixes différents `q4`/`q8`), ici `base` seul suffirait à
    provoquer une collision si le regroupement oubliait `total` — c'est cette régression précise
    que ce test attrape.
    """
    fichiers = [
        _fichier("modele-00001-of-00002.gguf"),
        _fichier("modele-00002-of-00002.gguf"),
        _fichier("modele-00001-of-00003.gguf"),
        _fichier("modele-00002-of-00003.gguf"),
        _fichier("modele-00003-of-00003.gguf"),
    ]

    resultat = parts_du_meme_modele("modele-00001-of-00002.gguf", fichiers)

    assert resultat == ["modele-00001-of-00002.gguf", "modele-00002-of-00002.gguf"]


def test_nom_ressemblant_a_une_part_sans_en_etre_une() -> None:
    """Trois formes proches du motif, aucune ne doit matcher : le motif est strict, pas indulgent.

    Chaque cas fournit un vrai « frère » dans le dépôt — un fichier qui SERAIT regroupé si le
    motif était assoupli sur ce point précis. Un fixture à un seul fichier ne prouverait rien : le
    résultat `[cible]` serait identique que le motif matche ou non, faute de partenaire à trouver.
    """
    # Bonne forme de rang/total, mauvaise extension : ce n'est pas un GGUF découpé.
    fichiers_extension = [
        _fichier("modele-00001-of-00003.safetensors"),
        _fichier("modele-00002-of-00003.safetensors"),
    ]
    assert parts_du_meme_modele("modele-00001-of-00003.safetensors", fichiers_extension) == [
        "modele-00001-of-00003.safetensors"
    ]

    # Rang à un seul chiffre plutôt que cinq : hors convention llama.cpp, traité comme un fichier seul.
    fichiers_rang_court = [_fichier("modele-1-of-3.gguf"), _fichier("modele-2-of-3.gguf")]
    assert parts_du_meme_modele("modele-1-of-3.gguf", fichiers_rang_court) == ["modele-1-of-3.gguf"]

    # Le mot « of » est présent mais aucun rang numérique ne l'entoure.
    assert parts_du_meme_modele("resume-of-modele.gguf", [_fichier("resume-of-modele.gguf")]) == [
        "resume-of-modele.gguf"
    ]


def test_parts_absentes_du_depot_ne_sont_pas_inventees() -> None:
    """Si une part annoncée par le nom n'est pas dans la liste réelle, elle n'est pas ajoutée."""
    fichiers = [_fichier("modele-00001-of-00003.gguf"), _fichier("modele-00002-of-00003.gguf")]

    resultat = parts_du_meme_modele("modele-00001-of-00003.gguf", fichiers)

    assert resultat == ["modele-00001-of-00003.gguf", "modele-00002-of-00003.gguf"]
    assert "modele-00003-of-00003.gguf" not in resultat


# ------------------------------------------------------- le total couvre toutes les parts


def test_octets_totaux_couvre_toutes_les_parts_pas_seulement_la_cible() -> None:
    """Le bug réel du 2026-08-14 : le total ne doit pas s'arrêter à la part cliquée.

    Trois parts de 100 Mo chacune : le total attendu est 300 Mo, que la cible pointe la première,
    la deuxième ou la troisième part.
    """
    un_cent_mo = 100 * 1024 * 1024
    fichiers = [
        _fichier("modele-00001-of-00003.gguf", un_cent_mo),
        _fichier("modele-00002-of-00003.gguf", un_cent_mo),
        _fichier("modele-00003-of-00003.gguf", un_cent_mo),
    ]

    for cible in (f.nom for f in fichiers):
        assert octets_totaux(fichiers, cible, []) == 3 * un_cent_mo


def test_octets_totaux_modele_a_une_seule_partie_ne_compte_que_lui_meme() -> None:
    """Un fichier non découpé : le total est sa propre taille, pas celle du dépôt entier."""
    fichiers = [_fichier("modele.gguf", 500), _fichier("mmproj-modele.gguf", 50)]

    assert octets_totaux(fichiers, "modele.gguf", []) == 500


def test_octets_totaux_rend_none_si_une_taille_de_part_manque() -> None:
    """Un pourcentage calculé sur un total incomplet vaut moins que pas de pourcentage du tout."""
    fichiers = [
        _fichier("modele-00001-of-00002.gguf", 100),
        _fichier("modele-00002-of-00002.gguf", None),
    ]

    assert octets_totaux(fichiers, "modele-00001-of-00002.gguf", []) is None


def test_octets_totaux_sans_cible_exclut_les_motifs_ignores() -> None:
    """Sans fichier ciblé (dépôt entier), le total suit `motifs`, pas le regroupement de parts."""
    fichiers = [_fichier("modele.gguf", 500), _fichier("README.md", 10)]

    assert octets_totaux(fichiers, None, ["*.md"]) == 500
