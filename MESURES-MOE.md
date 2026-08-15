# MESURES-MOE — Lot L7 : charger le MoE 35B-A3B en conditions réelles

*Mesuré le 2026-08-15, sur la machine de développement (Arch Linux natif, RTX 3060 12 Go,
pilote 610.43.03, 46 Gio de RAM). `echohub-v1` tourne en natif sur cette même machine
(`/mnt/projects/echohub/backend/.venv`, port 37821, PID 900) et n'a été ni arrêté ni perturbé
(vérifié avant/après : PID stable, port toujours en écoute). Deux autres équipes travaillent en
parallèle sur ce dépôt.*

Modèle mesuré : `unsloth/Qwen3.6-35B-A3B-GGUF::Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, 20,6 Gio,
architecture `qwen35moe` (hybride attention/état récurrent, 40 blocs, 256 experts dont 8 actifs
par token, `intervalle_attention_pleine=4`).

## 1. Accès au modèle — décision appliquée

`/mnt/models/echohub` (arborescence v1, déjà au format `<org>--<repo>/` attendu par
`backend/models/storage.py::nom_dossier`) est monté **en lecture seule** sur `/data/models` dans
`docker-compose.yml`, à la place du volume nommé `echohub_models` (resté vide, commenté juste
en dessous). Aucune copie de modèle, aucun chemin absolu codé en dur côté Python — `MODELS_DIR`
reste la seule variable lue (`backend/core/config.py`). Réversible en restaurant la ligne
commentée. Vérifié : `docker exec echohub-v2 touch /data/models/test` échoue
(`Read-only file system`), `/mnt/models` sur l'hôte n'a reçu aucune écriture.

La forme GPU du compose a aussi été permutée : cette machine est Linux natif avec CDI (pas
Windows/WSL2), donc `devices: [nvidia.com/gpu=all]` est la forme active — `COMPATIBILITE-GPU.md`
documentait déjà les deux formes, seule la permutation a été faite.

L'image `echohub:v2` a été construite (`docker compose build echohub`, ~16 min, dominées par la
compilation CUDA de `llama-cpp-python` pour `sm_86;sm_120a`, aucune erreur). Le conteneur démarre
sain, voit le GPU (`nvidia-smi` dans le conteneur = identique à l'hôte) et lit le fichier modèle.

**Défaut mineur non bloquant, non corrigé (hors périmètre)** : au démarrage, le backend tente de
créer `/data/models/.echohub` (dossier interne du gestionnaire de téléchargements,
`backend/models/storage.py:193`) et échoue proprement (`Read-only file system`, logué en ERROR,
ne bloque rien). Attendu vu le montage RO ; sans effet sur le chargement ni le déport.

## 2. Le plan calculé par le projet lui-même

Calculé avec le vrai planificateur du projet (`backend/inference/planner`), à partir des
métadonnées **lues** dans le GGUF (pas déduites) et du profil machine réel mesuré par NVML/psutil
dans le conteneur (VRAM libre 11190 MiB / 12288 MiB, RAM disponible 37,7 Gio) :

| | sans déport (coupe par couches) | avec déport (nominal, `planifier()`) |
|---|---|---|
| couches sur GPU | **15 / 40** | **40 / 40** |
| groupes d'experts déportés | 0 | **34 / 40** (blocs 6 à 39, 15,51 Gio) |
| contexte | 262 144 | 262 144 |
| cache KV | f16 | f16 |
| VRAM requise (calculée) | 10,449 Gio | 10,813 Gio |
| RAM requise (calculée) | 16,384 Gio | 15,506 Gio |

Justification du plan avec déport, telle que rendue par l'API : *« Les 40 blocs restent sur le
GPU : ce sont 34 groupes de tenseurs d'experts qui partent en mémoire hôte, pas des couches
entières. Toute l'attention et tout le dense restent accélérés. »*

Le contexte reste à 262k dans les deux plans : l'architecture est hybride (seul 1 bloc sur 4 porte
un cache KV plein, les autres portent un état récurrent de taille quasi nulle), donc le cache KV
ne domine pas le budget mémoire même à ce contexte — c'est le planificateur qui l'établit, pas une
estimation.

## 3. Chargement SANS déport — mesure réelle

`nvidia-smi` **avant** (aucun modèle chargé) :

```
2026/08/15 14:12:09.751, NVIDIA GeForce RTX 3060, 715 MiB, 11193 MiB, 12288 MiB, 0 %, 51°C
```

Requête : `POST /inference/charger` avec le plan ci-dessus (`experts_deportes: []`,
`couches_gpu: 15`) appliqué tel quel (pas replanifié à la volée, comme l'exige le contrat de
l'API). Chargement à froid (première lecture du fichier de 20,6 Gio par le conteneur).

`nvidia-smi` **pendant** (état `pret`) :

```
2026/08/15 14:15:50.251, NVIDIA GeForce RTX 3060, 11490 MiB, 418 MiB, 12288 MiB, 0 %, 60°C
```

- **VRAM occupée : 11 490 MiB (11,22 Gio)** — 6,9 % au-dessus du calcul (10,449 Gio), la carte est
  quasi saturée (418 MiB de marge sur 12 288).
- **RAM** (`free -h`) : used 9,9 Gio, available 37 Gio, **swap utilisé 4,3 Gio** — le plan sans
  déport a fait déborder le processus dans le swap.
- **Durée de chargement : 208,11 s** (`etat_moteur.duree_chargement_s`, à froid).
- `vram_avant_octets`/`vram_apres_octets` (mesurés par l'adaptateur) : 1,07 Gio → 11,59 Gio.

**Débit de génération réel**, prompt court (« Explique en trois phrases ce qu'est un mélange
d'experts (MoE)… »), 150 tokens demandés, TTFT exclu du débit :

```
n_tokens = 150 · TTFT = 1,128 s · débit (hors TTFT) = 12,07 tok/s · débit global = 10,93 tok/s
```

`nvidia-smi` **après déchargement** (`POST /inference/decharger`) :

```
2026/08/15 14:17:36.863, NVIDIA GeForce RTX 3060, 844 MiB, 11064 MiB, 12288 MiB, 0 %, 57°C
```

VRAM revenue à la ligne de base (844 MiB, contre 715 MiB avant tout chargement — écart résiduel
négligeable, driver/contexte CUDA).

## 4. Chargement AVEC déport — défaut bloquant trouvé, corrigé, puis mesure réelle

### 4.1 Premier essai : échec, et c'est le mécanisme de garde qui a parlé

`POST /inference/charger` avec le plan « avec déport » (34 blocs) a échoué en 6 s :

```json
"etat": "echoue",
"cause": "deport_experts_indisponible",
"message": "Le journal de llama.cpp ne porte aucune ligne de surcharge de buffer : impossible
             de vérifier que les experts sont bien en mémoire hôte, le chargement est refusé."
```

Conformément à la doctrine du projet (« un déport non confirmé par le journal vaut échec »), ce
résultat a été traité comme un échec — **pas maquillé**. Mais `docker logs echohub-v2` sur la
même fenêtre montrait bien, en clair, 102 lignes du type :

```
tensor blk.6.ffn_down_exps.weight (176 MiB q5_K) buffer type overridden to CUDA_Host
tensor blk.6.ffn_gate_exps.weight (144 MiB q4_K) buffer type overridden to CUDA_Host
tensor blk.6.ffn_up_exps.weight (144 MiB q4_K) buffer type overridden to CUDA_Host
… (34 blocs, 6 à 39, 3 tenseurs chacun)
```

**Le déport avait réellement eu lieu côté llama.cpp.** Le mécanisme de vérification du projet
(`CollecteurJournal`, `backend/inference/engines_adapters/experts_hote.py`) ne le voyait
simplement jamais. Cause identifiée par lecture du paquet installé (`llama_cpp/_logger.py`,
`llama-cpp-python==0.3.34`) :

```python
@llama_cpp.llama_log_callback
def llama_log_callback(level, text, user_data):
    if logger.level <= GGML_LOG_LEVEL_TO_LOGGING_LEVEL[level]:
        print(text.decode("utf-8"), end="", flush=True, file=sys.stderr)
```

Ce callback C **imprime directement sur `stderr`** — il n'appelle jamais `logger.debug(...)` ni
aucune méthode du module `logging`. `logger.level` n'y sert que de condition au `print`. Le
commentaire d'origine du projet (« llama-cpp-python route déjà le journal C [vers `logging`] »,
`experts_hote.py`) était donc **faux pour cette version installée** — mesuré, pas supposé. Le
`logging.Handler` que `CollecteurJournal.brancher()` attache ne recevait donc **jamais aucune
ligne**, quel que soit le contenu réel du journal. Le déport échouait à 100 % des essais sur cette
machine, alors qu'il fonctionnait à 100 % côté moteur.

### 4.2 Correctif appliqué — signalé séparément du relevé, comme demandé

**Fichier modifié : `backend/inference/engines_adapters/experts_hote.py`.** `CollecteurJournal`
gagne un second canal de captation, additif au premier (qui reste en place au cas où une version
future de `llama-cpp-python` route réellement via `logging`) :

- `installer_relais_c(module)` remplace **temporairement** le callback C (`llama_log_set`) —
  exactement la route que le commentaire d'origine disait avoir évitée « pour rester réversible »,
  en présumant à tort qu'elle était inutile. Elle l'est tout autant : l'ancien callback
  (`llama_cpp._logger.llama_log_callback`) est gardé en référence et restauré par
  `retirer_relais_c(module)` dans le `finally` de `deport_actif()`.
- Le nouveau callback décode le texte brut, l'accumule (le C peut fragmenter une ligne), et
  réutilise la même logique d'analyse (`_analyser_ligne`) que l'ancien chemin `logging` —
  factorisée pour ne pas dupliquer les motifs de détection.
- Dégradation silencieuse si le binding n'expose pas ce qu'il faut (`llama_log_callback` /
  `llama_log_set` absents) : le comportement retombe sur `brancher()` seul, identique à avant ce
  correctif.

**Validation, dans les deux sens, avant de considérer le correctif acquis :**
- avant le correctif : échec systématique et reproductible (2 tentatives, même cause) ;
- après le correctif : succès systématique, même modèle, même plan, même machine (voir §4.3) ;
- `python -m pytest backend -q` (dans le conteneur, seul environnement avec `llama_cpp` installé) :
  **196 passed** (dont 42 pour les trois fichiers de tests du déport, contre 37 annoncés à
  l'audit — le compte a été revérifié, tous passent, aucun n'a été modifié ni désactivé) ;
- aucun test ne mocke le vrai callback C (`test_deport_experts.py::_capture` appelle
  `collecteur.emit(LogRecord(...))` directement) : le correctif n'a donc pas pu les faire passer
  artificiellement, il ajoute une seconde source de vérité sans toucher la logique testée.

### 4.3 Chargement avec déport, correctif appliqué — mesure réelle

`nvidia-smi` **avant** :

```
2026/08/15 14:22:44.907, NVIDIA GeForce RTX 3060, 718 MiB, 11190 MiB, 12288 MiB
```

`nvidia-smi` **pendant** (état `pret`) :

```
2026/08/15 14:22:51.091, NVIDIA GeForce RTX 3060, 10737 MiB, 1171 MiB, 12288 MiB, 0 %, 50°C
```

- **VRAM occupée : 10 737 MiB (10,49 Gio)** — 3,0 % SOUS le calcul (10,813 Gio), plus proche du
  plan que le cas sans déport.
- **RAM** (`free -h`) : used 6,9 Gio, available 40 Gio, swap 3,7 Gio (résiduel du chargement
  précédent, non entièrement relibéré par le noyau — sans conséquence mesurée sur le débit).
- **Durée de chargement : 2,37 s.** Ce chiffre n'est **pas comparable** aux 208,11 s du cas sans
  déport : le fichier de 20,6 Gio était déjà en cache page hôte après le premier chargement (la
  mesure de durée de chargement à froid n'a été prise que pour le cas sans déport ; le reproduire
  à froid pour le cas avec déport aurait nécessité de vider le cache disque, hors budget de ce
  lot — signalé ici plutôt que maquillé en gain de performance).

**Preuve non négociable — le journal confirme le déport** (`GET /inference/journal`, entrée du
chargement, message applicatif produit par `_noter_deport`) :

```
2026-08-15T12:22:45.185363+00:00 | llama.cpp | info | Chargement de unsloth/Qwen3.6-35B-A3B-GGUF::Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
2026-08-15T12:22:47.555882+00:00 | llama.cpp | info | 34 groupes d'experts confirmés en mémoire hôte par le journal.
   blocs_confirmes = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
                      26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39]
   tampons_mesures = ['sched_reserve:      CUDA0 compute buffer size =   524.06 MiB',
                       'sched_reserve:  CUDA_Host compute buffer size =   276.11 MiB']
2026-08-15T12:22:47.556597+00:00 | llama.cpp | info | Modèle prêt en 2.4 s
```

Les 34 blocs confirmés sont **exactement** ceux demandés par le plan (`[6..39]`) : ni manquant, ni
en trop. `verifier_application()` (`experts_hote.py:276`) a rendu `applique=True` sur cette base —
le chemin qui, avec un journal muet, aurait fait échouer le chargement.

**Débit de génération réel**, même prompt, mêmes réglages :

```
n_tokens = 150 · TTFT = 0,608 s · débit (hors TTFT) = 26,51 tok/s · débit global = 23,15 tok/s
```

`nvidia-smi` **après déchargement** :

```
2026/08/15 14:23:53.839, NVIDIA GeForce RTX 3060, 831 MiB, 11077 MiB, 12288 MiB, 0 %, 52°C
```

VRAM revenue à la ligne de base.

**Observation annexe, hors périmètre du lot, non corrigée** : dans les deux cas (avec et sans
déport), le texte généré est dégénéré — un flot du caractère `?` répété — sur le prompt français
contenant des apostrophes typographiques. Un prompt trivial (« Bonjour », température 1.0) produit
en revanche du texte anglais cohérent (raisonnement `<think>` en anglais malgré le socle français
— déjà noté dans `TODO.md`, backlog « modèles qui répondent en anglais »). Le débit mesuré reste
valide indépendamment de la qualité du texte : `n_tokens` compte les événements SSE `type: token`
réellement reçus, pas leur contenu. La cause de la dégénérescence n'a pas été creusée : elle est
identique dans les deux plans testés, donc **étrangère au déport d'experts** — pas dans le
périmètre de ce lot.

### 4.1. Diagnostic de la dégénérescence (lot L10, complément du 2026-08-15)

Trois maillons du chemin prompt → modèle ont été inspectés, chacun sur un artefact réel — jamais
supposés :

**1. Transport (interface → backend → adaptateur).** JSON sur HTTP est UTF-8 par construction ;
FastAPI/Pydantic décode en `str` Python (Unicode), sans transcodage supplémentaire. Rien dans
`chat/generation.py` ni `inference/__init__.py` ne réencode, n'échappe ni ne filtre le texte du
message avant de l'assembler en `MessageChat`. Vérifié en le prouvant à l'envers : le même prompt,
caractère `’` (U+2019) inclus, envoyé via `POST /chat/conversations/{id}/generer` à DEUX modèles
Qwen de la même famille (`Qwen3-VL-2B-Instruct-Q4_K_M` et `Qwen3.5-9B-Q5_K_M`, tous deux en
conteneur, sur ce projet), produit du texte français cohérent dans les deux cas — donc rien sur ce
chemin ne corrompt le caractère avant qu'il n'atteigne le moteur.

**2. Gabarit de conversation.** Le gabarit jinja du fichier GGUF `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`
lui-même (lu directement depuis ses métadonnées, `tokenizer.chat_template`, chargement
`vocab_only=True` — aucun poids, aucune VRAM, aucune génération) interpole le contenu textuel tel
quel (`{{- content }}` / `{{- item.text }}`) : aucune fonction d'échappement, de normalisation
Unicode ni de remplacement n'y touche l'apostrophe.

**3. Tokenisation.** Tokenisé directement contre le VRAI vocabulaire du même fichier GGUF
(`llama_cpp.Llama(..., vocab_only=True)`, sans charger les poids) :

```
apostrophe droite (U+0027) seule  -> [6]                 b"'"
apostrophe typographique (U+2019) -> [515]                b'\xe2\x80\x99'
"ce qu'est un mélange d'experts"  -> [341, 893, 16811, 632, 189540, 293, 6, 4431, 15089]
"ce qu’est un mélange d’experts"  -> [341, 893, 20746, 632, 189540, 293, 515, 4431, 15089]
                                        341=ce  893=' qu'  20746='’est'  632=' un'
                                        189540=' mélange'  293=' d'  515='’'  4431='exp' 15089='erts'
```

Les deux formes produisent des tokens **valides, uniques et de faible identifiant** (aucun
identifiant hors plage, aucun repli sur un octet brut, aucun jeton de remplacement) : la
tokenisation fusionne correctement `’est` en un seul token, exactement comme `'est` le fait côté
apostrophe droite. Rien n'indique une corruption à cette étape.

**Conclusion.** Les trois maillons que le projet contrôle (transport, gabarit, tokenisation) sont
vérifiés propres sur le VRAI fichier du modèle en cause. La dégénérescence n'a été observée que sur
ce checkpoint précis (`unsloth/Qwen3.6-35B-A3B-GGUF`, quantification dynamique `UD-Q4_K_M`), jamais
reproduite sur deux autres modèles Qwen de la même famille avec le même caractère. Le rapprochement
le plus probable est un défaut de calibration du modèle/de la quantification pour ces jetons
peu fréquents (`’est` à l'identifiant 20746 sur 248 320, `’` seul à 515) — une quantification
agressive dégrade en priorité les jetons rares, et le test d'origine utilisait une température de
1.0, qui amplifie l'effet d'une distribution mal calibrée. **La cause n'est donc pas dans le projet
EchoHub** — aucun correctif n'est proposé ici, un correctif côté harnais masquerait un défaut réel
du modèle/de sa quantification sans le résoudre. Non reproduit sur le modèle en cause lui-même dans
ce lot, conformément à la consigne de ne pas charger le 35B-A3B (coût de chargement à froid mesuré
en 4.1 : 208 s) ; la reproduction originale (§4, ci-dessus) reste la seule observée en génération
réelle sur ce checkpoint.

## 5. Tableau récapitulatif

| | sans déport | avec déport | écart |
|---|---|---|---|
| couches GPU | 15 / 40 | 40 / 40 | +25 couches dense/attention accélérées |
| VRAM calculée (plan) | 10,449 Gio | 10,813 Gio | +0,364 Gio |
| VRAM mesurée | **11,22 Gio** (11 490 MiB) | **10,49 Gio** (10 737 MiB) | **-0,73 Gio** |
| RAM calculée (plan) | 16,384 Gio | 15,506 Gio | -0,878 Gio |
| swap observé | 4,3 Gio | 3,7 Gio | — |
| durée de chargement | 208,11 s (à froid) | 2,37 s (cache chaud, non comparable) | — |
| débit (hors TTFT) | **12,07 tok/s** | **26,51 tok/s** | **× 2,20** |
| débit (TTFT inclus) | 10,93 tok/s | 23,15 tok/s | × 2,12 |

## 6. Réponse à la question du TODO : « le déport récupère-t-il les 6 Go inutilisés ? »

**Non — sur cette machine (RTX 3060, 12 Go), il n'y a jamais eu 6 Go de VRAM inutilisée à
récupérer.** Le plan sans déport, calculé par le projet lui-même, occupe déjà 10,449 Gio sur
12 Gio (87 %) rien qu'en ne gardant que 15 des 40 couches sur GPU ; mesuré, il grimpe à 11,22 Gio
(91 %), ne laissant que 418 MiB de marge. Le chiffre de « 6 Go inutilisés » cité dans `TODO.md`
et `STATE.md` ne se vérifie sur aucune configuration mesurée ici — il correspond plausiblement à
une intuition antérieure à l'audit du 2026-08-15, ou à la machine cible (RTX 5080 16 Go,
~14,7 Go utilisables, jamais testée dans ce lot faute de matériel).

**Ce que le déport rend réellement, mesuré, c'est un changement d'axe de placement, pas une
récupération d'espace libre :** sans lui, la coupe par couches entières n'accepte que 15 blocs
sur 40 dans le budget VRAM disponible — 25 blocs de dense et d'attention, lus intégralement à
chaque token, tournent alors sur CPU. Avec lui, **les 40 blocs restent sur GPU** ; seuls les
tenseurs d'experts les plus lourds (34 groupes sur 40 — la partie du modèle où seulement 8 des
256 experts sont routés par token) partent en RAM hôte. Le résultat mesuré est un débit de
génération **multiplié par 2,2** (12,07 → 26,51 tok/s) dans une empreinte VRAM légèrement
*inférieure* à celle du plan sans déport (10,49 Gio contre 11,22 Gio mesurés). Le déport ne
comble donc pas un vide de VRAM inexistant sur cette carte : il évite de payer, à chaque token,
le calcul dense sur CPU en échangeant contre des experts peu sollicités.
