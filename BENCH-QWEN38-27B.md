> Mesure effectuée le 18 août 2026.
> Modèle évalué puis laissé de côté, non retenu pour un usage courant en raison de son débit.

# BENCH-QWEN38-27B — Qwen3.8-27B Q4_K_M en local, RTX 3060 12 Go

*Mesuré le 2026-08-18, sur la machine de développement (Arch Linux natif, RTX 3060 12 Go,
46 Gio de RAM, CPU AMD Ryzen 5 2600 six coeurs). `echohub-v1` tourne en natif sur cette même
machine et n'a été ni arrêté ni perturbé pour ce mandat.*

## 1. Modèle téléchargé

| | |
|---|---|
| Dépôt HuggingFace | `unsloth/Qwen3.8-27B-GGUF` (dépôt de référence demandé — exposait bien un Q4_K_M, pas de repli sur bartowski nécessaire) |
| Fichier | `Qwen3.8-27B-Q4_K_M.gguf`, fichier unique, aucun shard |
| Taille disque | 17 106 775 008 octets (15,92 GiB, 5,01 bits/poids) — identique à la taille annoncée par l'API HuggingFace (`ls` du dépôt) |
| Emplacement | `/mnt/models/echohub/unsloth--Qwen3.8-27B-GGUF/Qwen3.8-27B-Q4_K_M.gguf` (convention `<org>--<repo>/` respectée) |
| Commande | `hf download unsloth/Qwen3.8-27B-GGUF Qwen3.8-27B-Q4_K_M.gguf --local-dir /mnt/models/echohub/unsloth--Qwen3.8-27B-GGUF` |
| Une seule quantisation téléchargée | Oui — aucune autre variante récupérée |
| Espace disque après | 397 Go libres sur `/mnt/models` (458 Go total, 38 Go utilisés) |

Métadonnées lues dans l'en-tête GGUF (pas déduites) :

| Clé GGUF | Valeur |
|---|---|
| `general.architecture` | `qwen35` |
| `qwen35.block_count` | **65** blocs |
| `qwen35.context_length` (natif) | 262 144 |
| `qwen35.embedding_length` | 5120 |
| `qwen35.attention.head_count` / `head_count_kv` | 24 / 4 (GQA) |
| `qwen35.full_attention_interval` | 4 — un bloc sur quatre porte une attention pleine, les autres un état récurrent (SSM/gated-deltanet) |
| `qwen35.ssm.*` (conv_kernel, state_size, group_count, inner_size) | présents — confirme l'architecture hybride état-récurrent |
| `qwen35.nextn_predict_layers` | 1 (tête MTP, non utilisée dans ce bench) |
| Nombre de paramètres | 27 320 697 856 (~27,3 B) |

## 2. Compatibilité llama.cpp — état des lieux et action prise

**EchoHub v1** (`/mnt/projects/echohub/backend/.venv`) embarque `llama-cpp-python 0.3.23`.
**EchoHub v2** (`/mnt/projects/echohub-v2/backend/.venv`, Python 3.14) embarque `llama-cpp-python
0.3.34`. Aucun des deux ne fournit de binaire CLI autonome (`llama-cli`/`llama-bench`) exploitable
hors du binding Python, et je n'ai pas cherché à établir si leur `libllama` embarquée connaît
l'architecture `qwen35` — **je n'ai touché à aucun des deux venvs**, conformément au mandat.

Un clone llama.cpp dédié existait déjà sous `/home/trinity/.unsloth/llama.cpp` (commit
`9a532ae4b`, build `b9222`, daté du 2026-05-18), avec un dossier `build-cuda` déjà configuré
(`GGML_CUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=86`, `Release`) mais dont seul `llama-server` avait été
compilé. J'ai vérifié dans les sources (`src/llama-arch.cpp`, `src/models/qwen35.cpp`,
`src/models/qwen3next.cpp`, `src/models/delta-net-base.cpp`) que l'architecture `qwen35` /
gated-deltanet **est bien supportée** par ce build — donc **aucune mise à jour de llama.cpp n'a
été nécessaire**, juste compléter la compilation.

**Ce que j'ai fait** : dans ce même emplacement dédié (`/home/trinity/.unsloth/llama.cpp/build-cuda`),
j'ai compilé les cibles manquantes `llama-cli`, `llama-bench` et `llama-completion` :
```
cmake --build build-cuda --target llama-cli llama-bench llama-completion -j12
```
Aucun fichier d'EchoHub v1 ou v2 n'a été modifié. Le chargement réel du modèle (§4) confirme la
compatibilité : `general.architecture = qwen35` charge et génère sans erreur.

## 3. Réglage de l'offload — `-ngl` sondé par essais réels

Sondage binaire par échec de chargement réel (pas de calcul théorique) :

| `-ngl` (contexte de test) | Résultat |
|---|---|
| 65 (tout GPU) | échec — `failed to load model` (VRAM insuffisante) |
| 45 | échec |
| 42 | échec — `failed to load model` |
| 41 (contexte court, 40 tokens) | **charge** |
| 40 (contexte de mesure 512+128=640) | échec — `failed to create context` (le KV cache du contexte de bench ne tient plus) |
| **39 (contexte de mesure 640)** | **charge — maximum retenu pour le bench** |

**Le maximum dépend du contexte demandé** : à contexte quasi nul, 41/65 couches tiennent ; au
contexte de mesure standard (640 tokens, prompt 512 + génération 128), la limite redescend à
**39/65**. C'est cette valeur, mesurée dans les conditions réelles du bench, qui sert de référence
« VRAM remplie au maximum sans déborder ».

## 4. Débit mesuré — `llama-bench`, trois réglages d'offload

Commande type (répétée pour chaque `-ngl`) :
```
llama-bench -m Qwen3.8-27B-Q4_K_M.gguf -ngl <N> -p 512 -n 128 -r 3 -o csv
```
Contexte de mesure : **640 tokens** (512 prompt + 128 génération, taille par défaut de
`llama-bench` = `n_prompt + n_gen`), cache KV `f16` sauf mention contraire.

| `-ngl` | couches GPU / CPU | Prompt processing (tok/s) | Génération (tok/s) |
|---|---|---|---|
| 20 | 20 / 45 | 211,8 ± 3,6 | 2,08 ± 0,001 |
| 30 | 30 / 35 | 238,9 ± 6,5 | 2,55 ± 0,03 |
| **39 (max)** | **39 / 26** | **273,9 ± 6,2** | **3,24 ± 0,03** |

**Effet de flash-attention et du cache KV quantisé**, testés à `-ngl 39` (le réglage optimal) :

| Variante | Prompt (tok/s) | Génération (tok/s) |
|---|---|---|
| Base (cache f16, sans FA) | 273,9 ± 6,2 | 3,24 ± 0,03 |
| `-fa 1` (flash-attention) | 278,4 ± 6,7 | 3,26 ± 0,01 |
| `-fa 1 -ctk q8_0 -ctv q8_0` (cache KV quantisé) | 275,9 ± 3,1 | 3,27 ± 0,04 |

**Aucun effet mesurable** au-delà du bruit de mesure (écarts-types qui se recouvrent). Explication
cohérente avec l'architecture : `full_attention_interval=4` — un bloc sur quatre seulement porte un
cache KV plein, les 3/4 restants portent un état récurrent de taille quasi nulle. Le cache KV ne
domine donc pas le budget mémoire à ce contexte, et ni FA ni sa quantisation ne peuvent y gagner
grand-chose. J'ai aussi vérifié que le cache KV quantisé ne permettait pas de pousser `-ngl`
au-delà de 39 au même contexte (`-ngl 41` et `43` avec `-fa 1 -ctk/-ctv q8_0` échouent toujours) —
confirme que c'est le poids des couches denses, pas le cache KV, qui borne l'offload ici.

## 5. VRAM et RAM réellement occupées (mesure directe, `-ngl 39`)

| | Avant chargement | Pendant l'inférence | Après déchargement |
|---|---|---|---|
| VRAM (`nvidia-smi`) | 1 378 MiB / 12 288 MiB | **11 812–11 833 MiB / 12 288 MiB** (marge de 75–95 MiB, quasi saturée) | 1 378 MiB |
| RAM `used` (`free -h`) | ~7,1–7,8 Gio | jusqu'à **8,9 Gio** | retombe |
| VmRSS du process (`/proc/<pid>/status`) pendant un run `llama-bench` | — | **16 781 MiB (16,4 Gio)** pic mesuré | — |

Note honnête sur la RAM : le modèle est chargé avec `mmap` actif (comportement par défaut). Le
`VmRSS` du process (16,4 Gio) reflète le fichier entier mappé en mémoire virtuelle, y compris la
portion copiée vers VRAM — ce n'est pas uniquement « la portion déportée sur CPU ». La colonne
`used` de `free -h` progresse peu car les pages du fichier modèle sur la portion CPU vivent
largement en page cache (`buff/cache`, resté stable à ~28 Gio tout du long, déjà chaud depuis le
téléchargement). Aucun swap observé (`free -h` : swap à 0 pendant toute la session).

CUDA rapporte un total VRAM utilisable de **11 907 MiB**, contre 12 288 MiB annoncés par
`nvidia-smi` — écart de 381 MiB réservé par le pilote/l'affichage, cohérent d'un bout à l'autre des
mesures.

## 6. Temps de chargement

Mesuré par `llama-completion` (`common_perf_print: load time`) : **3,06–3,09 s** à `-ngl 39`.

**Réserve** : cette mesure est à cache-disque chaud — le fichier venait d'être téléchargé
(donc déjà en page cache Linux) et plusieurs chargements successifs ont eu lieu dans la même
session. Le temps de chargement à froid (première lecture depuis le disque, cache vidé) **n'a pas
été isolé séparément** — je n'ai pas les droits root nécessaires pour vider le cache page
(`drop_caches`) sur cette machine, et je n'ai pas voulu redémarrer quoi que ce soit. À déclarer
« non obtenu », pas estimé.

## 7. Génération réelle — extrait de sortie

Commande :
```
llama-completion -m Qwen3.8-27B-Q4_K_M.gguf -ngl 39 -c 4096 -n 500 --temp 0.7 \
  -p "Explique en trois phrases ce qu'est une architecture hybride gated-deltanet dans un LLM."
```

Extrait réel généré (le modèle a un mode « thinking » actif par défaut ; à 500 tokens il n'avait
pas encore atteint sa réponse finale visible, mais le texte est cohérent et techniquement correct
— preuve que l'inférence tourne, pas un artefact de chargement) :

> *[Start thinking]* The user asks me to explain in three sentences what a "hybrid gated-deltanet
> architecture in an LLM" is. [...] **DeltaNet**: This is a linear attention mechanism [...] It
> uses a "delta rule" for updating a state matrix, allowing it to selectively overwrite information
> in its state [...] It achieves O(n) complexity in sequence length [...] **Gated mechanisms**: [...]
> Mamba uses a selective mechanism (gating) to decide what to remember/forget. [...] **Hybrid
> architecture**: [...] combining different types of layers - for example, mixing attention layers
> with SSM/linear attention layers. Think of models like Jamba [...] or Griffin [...] A "hybrid
> gated-deltanet" architecture would likely combine standard [...] attention layers with gated
> DeltaNet layers.

Mesure de perf associée à cette génération (`common_perf_print`, 30 tokens de prompt + 499 générés) :
`load time = 3061,09 ms` · `prompt eval = 8,69 tok/s` (prompt très court, overhead dominant) ·
`eval = 3,24 tok/s` — cohérent à ±1 % avec la mesure `llama-bench` (§4).

## 8. Contexte de mesure

- `llama-bench` (§4) : 640 tokens (512 prompt + 128 génération), `n_batch=2048`, `n_ubatch=512`.
- `llama-completion` (§7, génération réelle) : `n_ctx=4096` réservé, ~530 tokens réellement
  consommés.
- Contexte natif du modèle (non testé, hors budget) : 262 144 tokens.

## 9. Existe-t-il un MoE Qwen3.8 chargeable sur cette machine ?

**Non.** Recherche documentaire sur le Hub HuggingFace (aucun téléchargement effectué) :

- Le seul MoE **officiel** est `Qwen/Qwen3.8-2.4T-A95B` (2,4 T paramètres totaux, 95 B actifs) —
  hors de portée confirmée, comme déjà établi.
- Des dérivés communautaires **élagués** (« REAP » — reduced expert pruning) existent :
  `hellohazime/Qwen3.8-2.4T-A95B-REAP-256GB-GGUF` (nom indicatif : ~256 Go), et une variante
  encore plus lourde `REAP-512GB`. Vérifié sur le dépôt : le fichier réel
  (`Qwen3.8-2.4T-A95B-REAP-256GB-IQ1_S.gguf`, quantisation **IQ1_S**, la plus basse possible)
  pèse **246 215 835 008 octets, soit 229 Gio** — même en pruning agressif et à 1 bit par poids,
  quinze fois la RAM système disponible (46 Gio) et vingt fois la VRAM.
- Les variantes `MLX-reap50/60/75-*bit` (`pipenetwork/…`) sont réservées à Apple Silicon (format
  MLX), inutilisables sur CUDA/llama.cpp.
- Les variantes `NVFP4` (`mgoin/…`, `RadixArk/…`, `esatapedico/…`) exigent une architecture
  **Blackwell** (compute capability ≥ 10.0) pour le format NVFP4 natif — la RTX 3060 est `sm_86`
  (Ampere), incompatible.
- Aucune variante trouvée ne descend à un ordre de grandeur compatible avec 12 Go VRAM + 48 Go RAM.

**Conclusion** : pas de MoE Qwen3.8 utilisable sur ce matériel, ni officiel ni communautaire. Le
27B dense Q4_K_M testé ici reste la seule option raisonnable de la famille sur cette machine.

## 10. Vérifications indépendantes demandées par l'orchestrateur

Contre-mesures faites sur cette même partition, indépendamment de ce que l'autre équipe a déclaré :

1. `/mnt/models/echohub/Jackrong--Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF` existe
   toujours, fichier `Qwen3.5-9B.Q5_K_M.gguf` présent, **6,1 Gio réels** (6 467 965 824 octets) — conforme.
2. `/mnt/models/echohub/bartowski--mlabonne_Qwen3-14B-abliterated-GGUF` existe toujours, fichier
   `mlabonne_Qwen3-14B-abliterated-Q4_0.gguf` présent, **8,0 Gio réels** (8 543 001 696 octets) — conforme.
3. `/mnt/models/echohub-finetune` contient toujours **21 sous-dossiers** — conforme.

Les trois points sont vrais. Aucune alerte à remonter en tête de rapport.

## Conclusion

**Le modèle tourne réellement sur cette machine mais reste sous le seuil confortable pour un usage
interactif quotidien : ~3,2 à 3,3 tokens/seconde en génération au réglage optimal mesuré, ce qui
correspond à plusieurs secondes d'attente par phrase — tolérable pour une tâche de fond, frustrant
pour un dialogue en temps réel.** Le réglage mesuré comme optimal est **`-ngl 39` sur 65 blocs**
(39 couches GPU, 26 couches CPU/RAM), qui sature la VRAM disponible (11,8/11,9 Gio) sans déborder,
pour un contexte de mesure de 640 tokens — ni flash-attention ni le cache KV quantisé n'apportent
de gain mesurable sur cette architecture hybride, où le cache KV n'est de toute façon pas le facteur
limitant. Pour aller plus vite sur cette carte, il faudrait soit une quantisation plus agressive
(Q3/Q2, au prix de la qualité), soit plus de VRAM.
