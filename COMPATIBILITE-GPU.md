# Compatibilité GPU — contraintes non négociables

Ce document condense ce qui a été **payé en échecs réels** sur la v1 : versions, contournements,
pièges de plateforme. Chaque point a été mesuré, pas déduit. Les sources primaires sont dans
`reference/v1/` (`DOCKER-BUILD-LOG.md`, `PORTAGE-WINDOWS.md`).

**Règle : ne rien changer ici sans une mesure qui contredit la mesure d'origine.** Un raisonnement
plausible ne suffit pas — c'est exactement ce qui a produit les défauts de la v1.

## Parc matériel visé

| Machine | GPU | Compute | VRAM | OS |
|---|---|---|---|---|
| Développement | RTX 3060 | `sm_86` | 12 Go | Arch Linux natif |
| Cible | RTX 5080 | `sm_120` (Blackwell) | **16 Go** | Windows 11 + Docker Desktop + WSL2 |

La doc v1 vise une RTX 5090 32 Go. **C'est faux pour la machine réelle** : 16 Go, soit ~14,7 Go
utilisables (le bureau Windows en occupe ~1,2). Toute estimation de taille héritée de la v1 est à
recalculer.

## Chaîne CUDA

- **Image de base : `nvidia/cuda:12.8.0-devel-ubuntu22.04`.** CUDA 12.8 est le **plancher** qui
  connaît `sm_120`. La variante `devel` est obligatoire — `runtime` n'a ni nvcc ni les en-têtes,
  donc pas de compilation de llama-cpp-python.
- **Pilote NVIDIA hôte ≥ 570** pour les RTX 50xx.
- **Sous WSL2, le pilote s'installe UNIQUEMENT côté Windows.** Installer un pilote NVIDIA Linux
  dans la distro casse le passthrough : le pilote Windows expose `libcuda.so` en stub côté Linux.

## llama-cpp-python — les deux pièges

```dockerfile
ENV CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=86;120 -DGGML_CUDA_FORCE_CUBLAS=ON" \
    FORCE_CMAKE=1
RUN pip install --no-cache-dir --force-reinstall --no-binary llama-cpp-python llama-cpp-python
```

1. **`--no-binary` est obligatoire** : le wheel PyPI par défaut est CPU-only. Sans lui, tout
   « fonctionne » mais rien ne touche le GPU.
2. **`GGML_CUDA_FORCE_CUBLAS=ON` n'est pas cosmétique.** Sans ce flag, `nvcc` de CUDA 12.8
   **segfault** en compilant `template-instances/mmq-instance-q2_k.cu` pour `compute_120a`. C'est
   un bug du compilateur, pas du code de ggml — vérifié que ce n'est pas un OOM déguisé. Le flag
   route les multiplications quantifiées vers cuBLAS et évite de compiler les kernels fautifs.
   Issues upstream : [llama.cpp#18331](https://github.com/ggml-org/llama.cpp/issues/18331),
   [llama.cpp#24399](https://github.com/ggml-org/llama.cpp/issues/24399).
   **Coût non mesuré** : perte de performance possible face aux kernels MMQ natifs. À réévaluer
   quand le bug nvcc sera corrigé en amont.

CMake convertit automatiquement `120` en `120a` (variante GeForce grand public). Vérification au
runtime : le binaire doit rapporter `CUDA : ARCHS = 860,1200 | FORCE_CUBLAS = 1`.

`unzip` doit être dans les paquets apt — l'installeur Bun en dépend et échoue sinon.

## vLLM — état vérifié le 2026-08-14

La v1 laissait le support Blackwell « non confirmé ». **Il est maintenant confirmé par mesure :**

```
vllm 0.21.0 · torch 2.11.0+cu130 · CUDA 13.0
GPU: RTX 5080 · capability (12, 0)
archs supportées: sm_75, sm_80, sm_86, sm_90, sm_100, sm_120
```

- Installé dans un **venv séparé** (Python 3.10), pas dans celui du backend : ses dépendances
  (torch, CUDA 13) entrent en conflit avec le reste.
- **`transformers` doit être en v5.** Les modèles récents déclarent un tokenizer
  `TokenizersBackend` que la v4 ne connaît pas → `ValueError` au démarrage. `xgrammar` déclare
  exiger `transformers<5` : cette borne est **trop stricte**, l'import fonctionne en v5 (vérifié).
- vLLM **préalloue** la VRAM et ne la rend qu'à l'arrêt. Sur 16 Go, aucune cohabitation possible
  avec un modèle llama.cpp chargé : il faut éjecter l'un avant l'autre. Le planificateur doit
  traiter le GPU comme une ressource exclusive.

## Exposition du GPU à Docker — dépend de la plateforme

C'est **inversé** entre les deux machines, et c'est un piège coûteux :

| Plateforme | Syntaxe qui marche | Syntaxe qui échoue |
|---|---|---|
| Linux natif + CDI seul | `devices: ["nvidia.com/gpu=all"]` | `--gpus all` → `AMD CDI spec not found` |
| **Windows + Docker Desktop + WSL2** | `deploy.resources.reservations.devices` | `nvidia.com/gpu=all` → `unresolvable CDI devices` |

Le compose doit gérer les deux, pas en figer une.

## Pièges WSL2 — mesurés le 2026-08-14

**`GGML_CUDA_ENABLE_UNIFIED_MEMORY=1` est nuisible sous WSL2.** Sur Linux natif, la mémoire
unifiée laisse les poids déborder du GPU vers la RAM. **WSL2 ne supporte pas l'oversubscription de
mémoire managée** : les allocations restent côté hôte.

Symptôme mesuré : 20 Go de RAM occupés, **VRAM figée à 2 Go**, plusieurs minutes de chargement,
modèle inutilisable. Après désactivation : chargement en 12 s, 14,8 Go réellement en VRAM,
19,6 tok/s. Détecter la plateforme via `/proc/version` (contient `microsoft`).

**RAM de WSL2** : plafonnée par défaut à ~50 % de l'hôte. Pour l'offload CPU, il faut un
`.wslconfig` explicite (`memory=22GB` sur une machine de 31 Go).

`pin_memory=False` est forcé sous WSL — vLLM le signale, c'est normal et non corrigeable.

## Performances mesurées — points de comparaison

| Modèle | GPU | Configuration | Débit |
|---|---|---|---|
| Qwen2.5-0.5B Q4_K_M | RTX 3060 | tout GPU | 83,3 tok/s |
| Qwen3.6-35B-A3B IQ4_XS | RTX 5080 | 29/41 couches, `n_ctx` 32768 | **41 tok/s** |
| Qwen3.6-35B-A3B IQ4_XS | RTX 5080 | 29/41 couches, `n_ctx` 57344 | **19,6 tok/s** |

Le contexte large coûte la moitié du débit. Un plan de chargement doit exposer cet arbitrage,
pas le subir.

## Métadonnées de modèle — ne jamais déduire

La v1 devinait le nombre de couches à partir du **nom de fichier**, par paliers de paramètres.
Sur Qwen3.6-35B-A3B : **80 couches estimées, 41 réelles**. Le poids par couche était supposé à
150 Mo : **436 Mo réels**.

Tout est lisible dans l'en-tête GGUF (`.block_count`, encodé `[len:u64][clé][type:u32][valeur]`).
**Lire, jamais estimer.**

De même, un `config.json` de modèle **peut mentir** : un AWQ rencontré déclarait une tour de
vision (`vision_config`, `intermediate_size: 4304` non divisible par le `group_size` 128) dont
**aucun poids n'existait** dans les safetensors. Croiser la config avec l'index des tenseurs.

## Dégrader, jamais escalader

Après un échec de chargement, la v1 **augmentait** les paramètres : contexte 55k → 131k,
`gpu_memory_utilization` 0.72 → 0.78 → 0.80. Elle escaladait vers le mur.

Un échec doit produire un plan **plus conservateur**, et l'échec suivant un plan encore plus
conservateur, jusqu'à un mode minimal garanti.
