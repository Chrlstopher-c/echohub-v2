# EchoHub v2

Reprise d'EchoHub, motivée par un constat mesuré sur la version précédente : la couche qui
décide **comment** charger un modèle est fausse par construction.

## Ce qui a motivé la reprise

Six défauts corrigés à la main sur la v1 en une session, tous de la même famille — des
constantes relevées sur une machine (RTX 3060, Linux natif) et transposées telles quelles :

| Défaut | Réalité mesurée |
|---|---|
| Couches déduites du nom de fichier par paliers | 80 estimées, **41** réelles |
| Poids par couche supposé à 150 Mo | **436 Mo** réels |
| Trois estimations concurrentes (frontend, router, service) | aucune ne lit le fichier |
| `GGML_CUDA_ENABLE_UNIFIED_MEMORY` posé sans détecter la plateforme | sous WSL2 : modèle en RAM, VRAM inutilisée |
| Paramètres **augmentés** après chaque échec de chargement | 55k → 131k de contexte, jusqu'au mur |
| `config.json` d'un modèle pris pour argent comptant | tour de vision déclarée, poids absents |

Aucun n'est un bug isolé : ce sont les symptômes d'une couche d'orchestration qui **devine**
ce qu'elle pourrait **lire**.

## Le principe de la v2

Un planificateur de chargement unique, qui mesure au lieu de supposer :

1. lire les métadonnées réelles du GGUF (architecture, `block_count`, taille) ;
2. mesurer la VRAM et la RAM réellement disponibles ;
3. détecter la plateforme (WSL2, Linux natif, pilote) et ses contraintes ;
4. produire un plan de chargement complet — couches GPU, contexte, batch, type de KV cache ;
5. **dégrader** après un échec, jamais escalader.

Source unique de vérité : le frontend l'affiche, il ne le recalcule pas.

## Ce qui est repris de la v1

Le `Dockerfile` — il compile `llama-cpp-python` avec le support CUDA pour Blackwell (`sm_120`)
et embarque le contournement d'un segfault de nvcc sur les kernels MMQ. C'est l'actif le plus
coûteux à reconstruire de la v1.

## État

Démarrage du projet — rien d'implémenté à ce stade.
