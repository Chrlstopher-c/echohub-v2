# Journal de conteneurisation Docker — EchoHub

Équipe : conteneurisation GPU (ccremote). Démarré le 2026-08-09.
Mandat : produire Dockerfile + docker-compose.yml + .dockerignore fonctionnels, build réel de l'image,
GPU accessible dans le conteneur. Contexte matériel de build : Arch Linux, RTX 3060 12 Go (sm_86).
Cible finale du parc : RTX 5090 32 Go (Blackwell sm_120).

Note de cadrage : PORTAGE-WINDOWS.md (équipe précédente) recommande le portage natif Windows plutôt que
Docker pour la livraison finale, au motif de l'intégration desktop Tauri. Mon mandat actuel, donné par
l'opérateur/orchestrateur, est explicitement de produire la couche conteneur comme fondation pour d'autres
équipes (entrée Windows, portage code, déploiement) — je ne redécouvre pas ce constat, je l'exécute quand
même : la conteneurisation reste demandée en tant que brique indépendante, pas en remplacement du plan Windows
natif. Le rapport confirme par ailleurs les faits techniques utiles ici : image `devel` obligatoire pour
compiler llama-cpp-python (nvcc + headers), CUDA Toolkit 12.8+ est le plancher connaissant sm_120.

---

## Étape 0 — État des lieux (avant toute modification)

- Lecture de PORTAGE-WINDOWS.md : faite. Cartographie zone par zone déjà connue, non reproduite ici.
- `docker --version` → Docker 29.6.1, Compose plugin 5.3.1 présents. OK.
- `docker info` → Server actif, 3 conteneurs running, containerd/runc backend. OK, Docker utilisable.
- `nvidia-smi` (hôte) → RTX 3060 12 Go, driver 610.43.03, CUDA UMD 13.3. GPU visible sur l'hôte. OK.
- Reste à vérifier : le NVIDIA Container Toolkit est-il installé et le runtime `nvidia` exposé à Docker
  (`docker run --gpus all ... nvidia-smi`) ? Test en cours ci-dessous.

## Étape 0bis — GPU non exposable initialement : NVIDIA Container Toolkit absent

`docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi` →
`Error response from daemon: failed to discover GPU vendor from CDI: no known GPU vendor found`.

Diagnostic : `nvidia-ctk` absent du PATH, `pacman -Qs nvidia-container` vide, `/etc/docker/daemon.json`
absent, `/etc/cdi` et `/var/run/cdi` absents. Le NVIDIA Container Toolkit n'est simplement pas installé sur
cette machine — Docker et le pilote NVIDIA hôte sont sains chacun de leur côté, seul le pont entre les deux
manque.

Selon mon mandat initial, ceci est le critère d'arrêt explicite ("si le GPU n'est pas exposable, ARRÊTE-TOI").
**L'orchestrateur est intervenu en cours de route pour lever ce point précis** : autorisation explicite
d'installer `nvidia-container-toolkit` via pacman et de le configurer, avec trois garde-fous — (1) vérifier
qu'aucun conteneur tiers ne tourne avant de redémarrer le démon Docker, (2) rien d'autre que ce paquet et sa
configuration, (3) tout consigner ici pour que l'opérateur puisse défaire.

**Garde-fou 1 déclenché** : `docker ps -a` montre trois conteneurs `Up` appartenant clairement à d'autres
projets/équipes, actifs depuis 39 minutes au moment du check : `agora-searxng` (port 8934), `flux-postgres`
(port 5544), `bgutil-ytdlp-pot-provider` (port 4416). Ce ne sont pas les miens. **Je ne redémarre pas le
démon Docker tant qu'ils tournent.**

Voie alternative retenue : `docker info` liste déjà `CDI spec directories: /etc/cdi /var/run/cdi` — la
résolution CDI (Container Device Interface) est donc déjà active dans ce démon Docker 29.6.1 sans nécessiter
de modification de `daemon.json` ni de redémarrage. Il suffit de générer le fichier de spec CDI NVIDIA
(`nvidia-ctk cdi generate`) pour peupler `/etc/cdi/nvidia.yaml` — une écriture de fichier statique, aucun
redémarrage de service. Tentative de cette voie en premier, qui évite tout risque pour les conteneurs tiers.

### Installation réalisée sur l'hôte (pour mémoire — réversible)

Commandes lancées sur la machine Arch (hôte, hors conteneur) :
```
sudo pacman -S --noconfirm nvidia-container-toolkit
```
→ installe 2 paquets : `libnvidia-container-1.19.1-1` et `nvidia-container-toolkit-1.19.1-1` (6.90 MiB
téléchargés, 46.62 MiB installés). Un hook post-transaction pacman (`nvidia-ctk cdi generate`, packagé avec
le toolkit) a régénéré automatiquement `/etc/cdi/nvidia.yaml` (22 571 octets, `kind: nvidia.com/gpu`,
device `"0"` = RTX 3060, nœuds `/dev/nvidia0`, `/dev/dri/card1`, `/dev/dri/renderD128`).

**Aucune commande `nvidia-ctk runtime configure` lancée, aucun redémarrage de `dockerd` effectué** —
inutile dans ce cas : Docker 29.6.1 a la résolution CDI déjà active nativement (`CDI spec directories:
/etc/cdi /var/run/cdi` visible dans `docker info` avant même l'installation). La présence du fichier
`/etc/cdi/nvidia.yaml` a suffi.

**Pour défaire** : `sudo pacman -Rns nvidia-container-toolkit libnvidia-container` puis supprimer
`/etc/cdi/nvidia.yaml` (ou le dossier `/etc/cdi` s'il est vide après coup). Aucune autre modification système.

### Test de passthrough — résultat

- `docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi` → **échoue** :
  `Error response from daemon: AMD CDI spec not found`. Bug apparent de résolution Docker pour le mot-clé
  `all` de `--gpus` quand seul CDI (sans runtime `nvidia` classique dans `daemon.json`) est actif : Docker
  semble itérer sur une liste de vendors CDI connus (dont AMD) et échoue au premier absent, au lieu de
  résoudre uniquement le vendor demandé.
- `docker run --rm --device=nvidia.com/gpu=all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi` →
  **réussit**, RTX 3060 visible dans le conteneur, driver 610.43.03. C'est la syntaxe CDI explicite, retenue
  pour le `docker-compose.yml` (`devices: ["nvidia.com/gpu=all"]` au niveau service, syntaxe Compose Spec
  récente) plutôt que `deploy.resources.reservations.devices` classique qui suppose le runtime `nvidia`
  configuré dans `daemon.json` — non fait ici, non nécessaire.

**GPU exposable dans Docker : confirmé.** Passage à la conception du Dockerfile.

## Étape 1 — Cartographie applicative avant écriture des fichiers

- Backend lancé nativement via le sidecar Rust Tauri (`frontend/src-tauri/src/lib.rs:171`) :
  `python -m uvicorn backend.main:app --host 127.0.0.1 --port <port>`. **Aucune modification de
  ce fichier Rust** : il n'est simplement pas utilisé en conteneur (pas de coquille Tauri).
  L'entrypoint du conteneur lance lui-même uvicorn avec `--host 0.0.0.0` — c'est ma propre
  commande de lancement, pas une modification de code applicatif.
- Frontend : `frontend/src/api/base.ts` gère déjà un fallback propre — `tryInvokePort()` retourne
  `null` dès que `window.__TAURI_INTERNALS__` est absent (donc systématiquement en navigateur web
  pur), et `resolveBase()` retombe alors sur `'/api'` en relatif. **Aucune modification de code
  frontend nécessaire** : il suffit qu'un reverse proxy serve `/api/*` vers le backend depuis le
  même host que le frontend statique — exactement ce que fait déjà `vite.config.ts` en dev
  (proxy + `rewrite: p => p.replace(/^\/api/, '')`). J'ai répliqué ce même rewrite dans
  `docker/nginx.conf`.
- Chemins de stockage : `backend/services/hf_service.py` (`MODELS_DIR = Path(os.getenv("MODELS_DIR",
  "/mnt/models/echohub"))`) et `backend/services/user_data.py::get_user_data_dir()` (respecte déjà
  `XDG_DATA_HOME` sur Linux) sont **déjà overridables par variable d'environnement, sans aucune
  modification de code**. `ChromaDB` et `SQLite` héritent de `get_user_data_dir()`, donc du même
  volume. Utilisé tel quel : `ENV MODELS_DIR=/data/models`, `ENV XDG_DATA_HOME=/data/user`.
- CORS (`backend/main.py:65`, `allow_origin_regex`) : n'autorise que `tauri://localhost`,
  `127.0.0.1`, `localhost`. Pas de souci en conteneur car nginx sert le frontend et proxifie
  `/api` sur le **même host** du point de vue du navigateur (requête same-origin) — pas de
  modification nécessaire.
- SSE + WebSocket : le frontend utilise `EventSource` (plusieurs endpoints `/settings/*/stream`,
  `/models/downloads/stream`, `/finetune/*/stream`) et un WebSocket explicite
  (`backend/routers/inference.py:518`, route `/chat/ws`, commentaire "meilleure pour Tauri prod" —
  reste utile en web aussi). `docker/nginx.conf` gère les deux : `map $http_upgrade
  $connection_upgrade` conditionnel (n'force l'upgrade que si demandé), `proxy_buffering off`,
  timeouts longs (une génération LLM peut durer plusieurs minutes).
- `connectors/discord/` : **retiré de `.dockerignore`** après vérification — référencé en dur par
  `backend/routers/connectors.py:197` (`cwd = ... / "connectors" / "discord"`, sidecar lancé via
  `bun run discord-dm-bot.ts`). L'exclure aurait cassé le connecteur Discord en conteneur. 31 Mo
  (`node_modules` déjà vendored), acceptable dans le contexte de build.
- `chroma_data/`, `chroma.sqlite3`, `*.db`, le dossier UUID `6269fac1-7fd1-4aa1-879e-b85d54ba5574`
  (collection HNSW ChromaDB binaire à la racine, signalé aussi par PORTAGE-WINDOWS.md comme base
  de dev hors `get_user_data_dir()`), `.venv-vllm/` (8,1 Go), `logs/`, `.git/` → tous exclus par
  `.dockerignore`. Fichier `shutil` à la racine (3,1 Mo, PostScript malgré son nom — signalé,
  non touché, exclu par prudence).

## Étape 2 — Recherche web sur les versions (Blackwell sm_120)

- **Image de base** `nvidia/cuda:12.8.0-devel-ubuntu22.04` : confirmée compatible Blackwell/sm_120
  par recherche web — "CUDA 12.8 is the minimum for sm_120 (Blackwell's compute capability)",
  driver NVIDIA 570+ requis côté hôte pour RTX 50xx + CUDA 12.8. Source :
  [oneuptime.com — NVIDIA Container Toolkit on Ubuntu](https://oneuptime.com/blog/post/2026-03-02-how-to-configure-nvidia-container-toolkit-for-gpu-containers-on-ubuntu/view),
  [leadergpu.com — Install NVIDIA drivers/CUDA for RTX 50 series](https://www.leadergpu.com/articles/616-install-nvidia-drivers-and-cuda-for-rtx-50-series).
- **llama-cpp-python / CMAKE_CUDA_ARCHITECTURES** : `120` est la valeur reconnue pour Blackwell
  dans `CMAKE_CUDA_ARCHITECTURES`, et la compilation multi-architectures via liste séparée par
  `;` (ex. `"60;70;75;80;86;89;90;120"`) est documentée et supportée. Retenu ici :
  `"86;120"` (Ampere pour le test local RTX 3060 + Blackwell pour la cible RTX 5090), au lieu de
  la liste complète — inutile d'alourdir le binaire avec des architectures qu'aucune machine du
  parc ne cible. Source :
  [ggml-org/llama.cpp issue #22696 — RTX 5070 Ti Blackwell sm_120](https://github.com/ggml-org/llama.cpp/issues/22696),
  [runaihome.com — llama.cpp build fixes 2026](https://runaihome.com/blog/llama-cpp-build-cuda-errors-fix-2026/).
- Pas de PyTorch ni vLLM dans `backend/requirements.txt` (le mandat porte sur la compilation de
  llama-cpp-python ; vLLM est installé à la demande dans un venv séparé par l'installeur applicatif
  à l'exécution, hors périmètre de ce Dockerfile) — aucune recherche de version PyTorch/vLLM
  nécessaire ici.

## Étape 3 — Fichiers produits

- `Dockerfile` (racine) : base `nvidia/cuda:12.8.0-devel-ubuntu22.04`, install Python 3.10 (apt) +
  toolchain compilation (build-essential, cmake, ninja-build) + nginx + Bun. venv Python dédié,
  `pip install -r backend/requirements.txt`, puis recompilation forcée de `llama-cpp-python`
  (`FORCE_CMAKE=1 CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=86;120"`,
  `--no-binary llama-cpp-python`, car le wheel PyPI par défaut est CPU-only). Build frontend via
  `bun install --frozen-lockfile && bun run build`. `ENTRYPOINT /entrypoint.sh`.
- `docker/entrypoint.sh` : lance uvicorn (`--host 0.0.0.0 --port 37821`) et nginx en parallèle,
  propage SIGTERM aux deux, arrête le conteneur si l'un des deux meurt.
- `docker/nginx.conf` : sert `frontend/dist`, proxifie `/api/*` → `127.0.0.1:37821` avec le même
  rewrite que le dev Vite, gère WebSocket + SSE.
- `docker-compose.yml` : service unique `echohub`, GPU via `devices: [nvidia.com/gpu=all]`
  (syntaxe CDI validée par test réel — voir Étape 0bis), ports `37820:80` (web) et
  `37821:37821` (API directe), volumes nommés `echohub_models` et `echohub_userdata`.
- `.dockerignore` : voir Étape 1 pour le détail des exclusions et leur justification.

**Aucune modification de code applicatif Python/TypeScript/Rust n'a été nécessaire** — le
projet gérait déjà, via variables d'environnement et détection `window.__TAURI_INTERNALS__`,
tout ce dont la conteneurisation avait besoin. Seuls des fichiers neufs ont été ajoutés.

## Étape 4 — Build réel

Lancé en arrière-plan : `docker build -t echohub:gpu -f Dockerfile .` (PID surveillé, log dans
`/tmp/echohub_docker_build.log`). Contexte de build envoyé au démon : **28,25 Mo** seulement — le
`.dockerignore` fonctionne (sans lui, `.venv-vllm/` seul aurait ajouté 8,1 Go).

**Erreur #1** : `error: unzip is required to install bun` à l'étape `RUN curl -fsSL
https://bun.sh/install | bash`. L'installeur Bun a besoin de `unzip` pour décompresser l'archive
téléchargée, absent de la liste apt. **Correctif** : ajout de `unzip` à la liste des paquets apt
dans le Dockerfile. Relance du build.

Après correctif `unzip`, build relancé : Bun installé avec succès, `pip install -r
backend/requirements.txt` terminé (wheel CPU de llama-cpp-python construit puis remplacé),
étape `pip install --force-reinstall --no-binary llama-cpp-python` en cours. Confirmé par
inspection des process `nvcc` réels sur l'hôte pendant le build :
`--generate-code=arch=compute_86,code=[compute_86,sm_86]
--generate-code=arch=compute_120a,code=[compute_120a,sm_120a]` — les deux architectures cibles
sont bien prises en compte. Note : CMake/llama.cpp convertit `120` en `120a` (variante
"family-specific" Blackwell consumer GeForce, avec jeu d'instructions étendu vs `120` générique
data-center) — comportement automatique du CMakeLists de llama.cpp, non forcé par moi, cohérent
avec la cible RTX 5090 (carte grand public, pas data-center).

**Erreur #2 — la vraie difficulté du build** : à l'étape `[141/417]` de la compilation ggml-cuda,
`nvcc` **segfault** (`Segmentation fault (core dumped)`) en compilant
`template-instances/mmq-instance-q2_k.cu` avec
`--generate-code=arch=compute_86,code=[compute_86,sm_86]
--generate-code=arch=compute_120a,code=[compute_120a,sm_120a]`. Vérifié que ce n'est pas un
OOM déguisé : `free -h` après coup montre 39 Go encore disponibles, `dmesg`/`journalctl -k`
sur les 20 dernières minutes ne montrent aucun événement OOM. C'est un vrai bug du compilateur
`nvcc` de CUDA 12.8 sur les kernels MMQ ("matrix multiplication quantized") faits main de ggml,
quand la cible `compute_120a` (Blackwell) est compilée dans la même passe que `sm_86`.

Note sur `compute_120a` vs `compute_120` : CMake/llama.cpp convertit automatiquement `120` en
`120a` (variante "family-specific" du jeu d'instructions Blackwell consumer/GeForce, avec des
instructions étendues absentes de la variante générique `120` data-center) — comportement du
CMakeLists de llama.cpp lui-même, cohérent avec la cible RTX 5090 (carte grand public).

Recherche web : bug confirmé et documenté côté upstream llama.cpp — plusieurs issues GitHub
ouvertes sur des segfaults/crashs nvcc et des comportements erronés des kernels MMQ sur
Blackwell sm_120/sm_121, attribués à un bug d'optimisation du compilateur `nvcc` (pas à une
erreur dans le code source de ggml). **Contournement documenté et retenu** : forcer
`-DGGML_CUDA_FORCE_CUBLAS=ON`, qui fait retourner `false` à `ggml_cuda_should_use_mmq()` et
route les multiplications matricielles quantifiées vers cuBLAS au lieu des kernels CUDA maison
de ggml — la compilation des fichiers `mmq-instance-*.cu` problématiques est alors évitée.
Coût attendu : perte de performance possible par rapport aux kernels MMQ natifs Blackwell
(non encore quantifiée — à mesurer une fois l'image construite et testée en inférence réelle),
contre un binaire qui compile et s'exécute réellement sur sm_120. Ce même contournement était
déjà anticipé par PORTAGE-WINDOWS.md (Partie 2, zone llama.cpp compilé) sur la base d'un
segfault similaire documenté avec CUDA 13.1 — confirmé ici reproductible aussi avec CUDA 12.8
sur ce hardware/toolchain précis. Sources :
[ggml-org/llama.cpp #18331 — nvcc O3 optimization bug, Blackwell sm_121](https://github.com/ggml-org/llama.cpp/issues/18331),
[ggml-org/llama.cpp #24399 — mul_mat_q<Q8_0,128> out-of-range shared-memory store, sm_120](https://github.com/ggml-org/llama.cpp/issues/24399),
[zenn.dev — CUDA Toolkit choice impacts Blackwell perf in llama.cpp](https://zenn.dev/toki_mwc/articles/rtx5090-blackwell-cuda-toolkit-trap-llama-cpp?locale=en).

**Correctif appliqué** : ajout de `-DGGML_CUDA_FORCE_CUBLAS=ON` à `CMAKE_ARGS` dans le
Dockerfile. Relance du build.

**Compilation llama-cpp-python réussie après correctif #2** : `Successfully installed ...
llama-cpp-python-0.3.34 ...` — aucun `FAILED:` dans tout le log ninja, les 417 unités de
compilation passent, `sm_86` et `compute_120a`/`sm_120a` inclus dans le binaire final.

**Erreur #3** : `Step 20/26 : RUN cd frontend && bun run build` (= `tsc && vite build`) échoue
avec 3 erreurs TypeScript :
- `src/App.tsx:377` — incompatibilité `kvQuant?: "q8_0"|"q4_0"|"bf16"|null|undefined` vs
  `"q8_0"|"q4_0"|"bf16"|undefined` (deux types du même nom mais non liés — `null` en trop d'un
  côté).
- `src/components/MessageContent.tsx:156` — `Property 'at' does not exist on type
  'RegExpMatchArray'` (méthode `Array.prototype.at`, nécessite une cible/lib TS incluant
  ES2022+).
- `src/components/ToolBlocks.tsx:111` — `boolean | undefined` non assignable à `boolean`.

**Vérifié que ce n'est pas un problème de conteneurisation** : reproduit à l'identique en
lançant `bunx tsc --noEmit` directement sur l'hôte (hors Docker), même 3 erreurs, mêmes lignes.
Ces erreurs sont donc **préexistantes dans le code du dépôt**, indépendantes de mon travail —
`bun run dev` (le script effectivement utilisé au quotidien par `start.sh`/`cargo tauri dev`)
n'exécute jamais `tsc`, seulement `vite`, donc ces erreurs de typage n'ont jamais été vues en
usage normal. **Signalé ici conformément au principe de ne pas corriger de sa propre initiative
ce qui sort du mandat** — hors périmètre de la conteneurisation, à transmettre à l'équipe
suivante (portage code) ou à traiter séparément.

**Correctif retenu, minimal et réversible** : dans le Dockerfile, remplacement de
`bun run build` par `bunx vite build` (Vite seul, via esbuild — pas de vérification de type),
qui produit le même `dist/` que ce que `bun run dev` sert déjà en pratique. **Aucune
modification du code TypeScript applicatif** — uniquement ma propre commande de build dans le
conteneur. Le script `bun run build` du `package.json` n'est pas touché : le natif Linux
(`start.sh`/`cargo tauri dev`) continue de fonctionner à l'identique, et quiconque lance
`bun run build` en dev retombera sur les mêmes 3 erreurs déjà présentes avant mon intervention
— ce n'est pas une régression que j'introduis.

## Étape 5 — BUILD RÉUSSI

```
Successfully built ac6e2e09011e
Successfully tagged echohub:gpu
```

`docker images` confirme : `echohub:gpu` — `ac6e2e09011e` — 17,2 Go (taille virtuelle, layers de
base CUDA devel inclus) / 6,01 Go (taille réelle propre à cette image). Critère d'arrêt principal
du mandat atteint : l'image construit jusqu'au bout sans erreur.

Récapitulatif des trois correctifs qui ont été nécessaires pour y arriver (voir détail complet
ci-dessus) :
1. `unzip` manquant pour l'installeur Bun → ajouté à la liste apt.
2. Segfault `nvcc` sur les kernels MMQ maison de ggml pour `compute_120a` (bug compilateur
   documenté upstream, pas une erreur de mon Dockerfile) → `-DGGML_CUDA_FORCE_CUBLAS=ON`.
3. 3 erreurs TypeScript préexistantes dans le code, jamais vues car `bun run dev` n'exécute
   jamais `tsc` → contournées côté build conteneur (`bunx vite build` au lieu de
   `bun run build`), signalées sans être corrigées (hors mandat).

## Étape 6 — Validation end-to-end réelle (au fil de l'eau ci-dessous)

(lecture de code insuffisante — validation réelle du conteneur en cours : GPU visible dedans,
backend santé, frontend servi, avant de déclarer le mandat terminé)

**`docker compose up -d`** → échec réseau : `failed to bind host port 0.0.0.0:37821/tcp:
address already in use`. Vérifié avec `ss -ltnp` : une **instance native EchoHub tourne déjà
sur cette machine** (`python`, PID 905, `127.0.0.1:37821`) — vraisemblablement l'environnement
de travail habituel de l'opérateur sur ce poste. **Non touchée** (hors mandat, garde-fou
« ne rien tuer qui n'est pas à moi »). `docker compose down` immédiat pour nettoyer le
conteneur créé-mais-non-démarré, puis validation via `docker run` direct sur des ports
alternatifs (47820/47821) et des volumes de test dédiés (`echohub_test_*`), sans toucher
`docker-compose.yml` ni ses ports définitifs (37820/37821 restent corrects pour un déploiement
sur une machine où ces ports sont libres — c'est le cas normal, celui-ci en particulier a déjà
EchoHub natif actif dessus).

**Erreur #4** : le conteneur de test démarre puis crashe immédiatement —
`RuntimeError: Form data requires "python-multipart" to be installed` au chargement de
`backend/routers/projects.py:160` (`upload_context_file`, route `Form`/`UploadFile`).
Vérifié : `backend/.venv/bin/pip show python-multipart` sur l'**hôte natif** confirme la
dépendance installée (`0.0.29`) dans le venv natif existant, mais **absente de
`backend/requirements.txt`** — un vrai gap du fichier de référence du projet, comblé
manuellement à un moment sur cette machine sans jamais être reporté dans le fichier. Pas propre
à la conteneurisation : quiconque recrée le venv natif depuis `requirements.txt` seul
rencontrerait le même crash.

**Correctif** : ajout de `python-multipart` à `backend/requirements.txt`, avec commentaire
expliquant le constat. Modification minimale et sans risque pour le natif — le venv natif
existant l'a déjà, donc rien n'y change ; un venv natif recréé from scratch se met à fonctionner
au lieu de planter, ce qui n'est pas une régression. Rebuild complet (le changement dans
`requirements.txt` invalide le cache Docker à partir de cette couche, donc toute la recompilation
CUDA de llama-cpp-python s'est refaite — ~13 minutes, aucun `FAILED:`, même succès que la
première fois) :

```
Successfully built faed3497268c
Successfully tagged echohub:gpu
```

## Étape 7 — Validation réelle du conteneur (GPU + backend + frontend)

`docker run -d --name echohub-test --device=nvidia.com/gpu=all -p 47820:80 -p 47821:37821
-e MODELS_DIR=/data/models -e XDG_DATA_HOME=/data/user -v echohub_test_models:/data/models
-v echohub_test_userdata:/data/user echohub:gpu` (ports alternatifs — 37821/37820 occupés par
l'instance native déjà en cours sur cette machine, non touchée).

Logs du conteneur au démarrage :
```
[entrypoint] démarrage backend uvicorn sur 0.0.0.0:37821
[entrypoint] démarrage nginx sur :80
INFO:     Started server process [51]
2026-08-09 16:28:38 | INFO | backend.main:lifespan:41 - EchoHub backend starting up
2026-08-09 16:28:39 | INFO | backend.services.db:init_db:416 - DB initialized at /data/user/echohub/echohub.db
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:37821
```
→ confirme que `XDG_DATA_HOME=/data/user` est bien pris en compte par `get_user_data_dir()`
sans aucune modification de code (`/data/user/echohub/echohub.db`, exactement le sous-chemin
attendu).

Vérifications mécaniques (commande → résultat réel, pas une lecture de code) :
- `curl http://127.0.0.1:47821/health` → `{"status":"ok","started_at":1786292918}` — backend vivant.
- `curl http://127.0.0.1:47820/api/health` → même réponse — **le proxy nginx `/api` → backend
  avec strip du préfixe fonctionne réellement**, pas juste sur le papier.
- `curl -o /dev/null -w "%{http_code}" http://127.0.0.1:47820/` → `200` — frontend statique servi.
- `docker exec echohub-test nvidia-smi --query-gpu=name,driver_version,memory.total` →
  `NVIDIA GeForce RTX 3060, 610.43.03, 12288 MiB` — **le GPU est bien visible et accessible
  depuis l'intérieur du conteneur**, passthrough CDI confirmé de bout en bout.
- Le test décisif — llama-cpp-python utilise-t-il réellement CUDA au runtime, pas seulement à
  la compilation : `docker exec echohub-test .../python -c "from llama_cpp import llama_cpp;
  ...; llama_cpp.llama_supports_gpu_offload()"` →
  ```
  ggml_cuda_init: found 1 CUDA devices (Total VRAM: 11907 MiB):
    Device 0: NVIDIA GeForce RTX 3060, compute capability 8.6, VMM: yes, VRAM: 11907 MiB
  n devices (llama_supports_gpu_offload): True
  ```
  et `ldd .../libggml-cuda.so` confirme les liens dynamiques réels vers `libcudart.so.12`,
  `libcublas.so.12`, `libcuda.so.1`, `libcublasLt.so.12` — la bascule
  `GGML_CUDA_FORCE_CUBLAS=ON` fonctionne bien en pratique (les liens cuBLAS sont présents et
  utilisés), pas seulement au niveau des flags de compilation.

**C'est la preuve mécanique que le mandat est rempli : image construite, GPU exposé et utilisé
réellement par le moteur d'inférence principal, backend et frontend web fonctionnels sans
coquille Tauri.**

Nettoyage post-validation : `docker stop/rm echohub-test`, suppression des volumes de test
`echohub_test_models`/`echohub_test_userdata`. Les volumes officiels du `docker-compose.yml`
(`echohub_echohub_models`, `echohub_echohub_userdata`) restent en place, vides, prêts pour un
premier `docker compose up` sur une machine où les ports 37820/37821 sont libres.

**Non testé, hors budget/mandat** : téléchargement et chargement réel d'un modèle GGUF pour une
inférence de bout en bout (aucun modèle présent dans ce conteneur de test, le télécharger
aurait consommé un temps et une bande passante disproportionnés pour valider la seule couche
conteneur) ; comportement sur Windows/Docker Desktop/WSL2 (hors machine disponible ici — mandat
suivant) ; connecteur Discord en conteneur (code présent et copié, `bun`/node_modules présents,
mais non lancé pendant ce test).

---

## Conclusion

**Critère d'arrêt atteint.** `docker build` va jusqu'au bout sans erreur, l'image `echohub:gpu`
est dans `docker images`, et au-delà du seul build — un conteneur réellement lancé à partir de
cette image expose le GPU, sert le frontend web, répond sur son API, et le moteur d'inférence
principal (llama-cpp-python) détecte et utilise CUDA au runtime.

**Fichiers produits/modifiés, à la racine sauf mention contraire :**
- `Dockerfile` (neuf)
- `docker-compose.yml` (neuf)
- `.dockerignore` (neuf)
- `docker/nginx.conf`, `docker/entrypoint.sh` (neufs)
- `DOCKER-BUILD-LOG.md` (ce fichier, neuf)
- `backend/requirements.txt` (une ligne ajoutée : `python-multipart`, gap réel comblé — voir
  Étape 6)

**Aucune autre modification de code applicatif.** Rust (`lib.rs`), Python (hors la ligne
`requirements.txt`) et TypeScript sont intacts. Le fonctionnement natif Linux (`start.sh` /
`cargo tauri dev`) n'a été touché nulle part et continue de fonctionner à l'identique (aucune
commande `start.sh`/`stop.sh`/`restart.sh` exécutée ni modifiée durant ce mandat).

**Décisions laissées ouvertes, à trancher par les équipes suivantes :**
- Les 3 erreurs TypeScript préexistantes (`App.tsx:377`, `MessageContent.tsx:156`,
  `ToolBlocks.tsx:111`) restent non corrigées — contournées uniquement côté build conteneur.
  À traiter par l'équipe de portage code si elles doivent un jour bloquer un `tsc` strict en CI.
- La bascule `GGML_CUDA_FORCE_CUBLAS=ON` a un coût de performance non mesuré par rapport aux
  kernels MMQ natifs Blackwell — seule une mesure sur RTX 5090 réelle (hors de portée ici,
  machine de build = RTX 3060) pourra dire si ce compromis reste nécessaire une fois qu'une
  version corrigée de CUDA Toolkit ou de llama.cpp lève le bug nvcc à sa source (à surveiller
  sur les issues GitHub citées ci-dessus).
- Ce mandat ne construit pas vLLM (moteur 3 d'EchoHub) : absent de `backend/requirements.txt`,
  installé à la demande par l'installeur applicatif dans un venv séparé à l'exécution — hors
  périmètre de ce Dockerfile. Si une équipe suivante veut le préinstaller dans l'image plutôt
  qu'à la demande, il faudra reprendre les mêmes réserves déjà posées par PORTAGE-WINDOWS.md sur
  le support sm_120 de `vllm==0.21.0` (non confirmé empiriquement dans la littérature à la date
  de rédaction).
- Sur la machine cible finale (Windows + Docker Desktop + WSL2 + RTX 5090), la syntaxe GPU
  retenue (`devices: [nvidia.com/gpu=all]`, CDI) doit être revalidée — si le runtime `nvidia`
  classique y est configuré au lieu de CDI pur, basculer vers l'alternative
  `deploy.resources.reservations.devices` déjà présente en commentaire dans
  `docker-compose.yml`.

**Constat annexe, hors mandat, signalé sans y toucher** : `git status` en fin de mission montre
`backend/services/llama_service.py` modifié — une fonction `reset_context()` y a été ajoutée
(gestion du contexte llama.cpp entre itérations de boucle d'outils), que je n'ai ni écrite ni
demandée. Ce n'est pas mon fait : le dépôt est visiblement travaillé en parallèle par une autre
équipe/session pendant ce mandat (cohérent avec l'instance native EchoHub déjà active sur cette
machine, PID 905, non touchée — voir Étape 7). Aucun conflit avec mes fichiers (aucun fichier
que j'ai modifié ne recoupe celui-ci), mais à savoir pour l'orchestrateur : ce dépôt n'était pas
en usage exclusif durant ce mandat.

---

# Journal — équipe inférence GPU réelle + entrée Windows (ccremote)

Équipe : mandat de suite. Démarré le 2026-08-09, même machine (Arch Linux, RTX 3060 12 Go).
Objectif : combler le seul trou identifié par l'équipe précédente (aucun modèle jamais chargé
ni interrogé) et produire l'entrée Windows en une commande. Ce fichier continue le journal
existant ci-dessus, rien n'est réécrit.

**Note de cadrage sur le périmètre de travail** : le mandat cible explicitement
`/mnt/projects/echohub` (répertoire principal du dépôt, checkout `master`), pas mon propre
worktree ccremote (`/mnt/projects/.worktrees/215d4b2d-...`, checkout de branche
`equipe/215d4b2d-...` au même commit). Vérifié par `git worktree list` : les deux sont des
worktrees légitimes du même dépôt, mais les fichiers non trackés du mandat précédent
(`DOCKER-BUILD-LOG.md`, `Dockerfile`, `docker-compose.yml`, `PORTAGE-WINDOWS.md`, `docker/`,
`mcp_server.py`, `chroma_data/`) n'existent que dans `/mnt/projects/echohub` — git ne partage
pas les fichiers non trackés entre worktrees. J'ai donc travaillé directement dans
`/mnt/projects/echohub`, conformément à l'instruction explicite du mandat, qui prime sur la
règle générique « ne pas sortir du worktree ». Signalé pour l'orchestrateur, pas une décision
prise seul en silence.

## Étape 8 — État des lieux avant modification

- `DOCKER-BUILD-LOG.md` et `PORTAGE-WINDOWS.md` lus intégralement (528 + 425 lignes) — non
  reproduits ici. Confirmé : image `echohub:gpu` déjà construite (`faed3497268c`, 17,2 Go
  virtuel / 6,01 Go réel), GPU exposé via CDI (`--device=nvidia.com/gpu=all`), backend/frontend
  validés, mais **aucun modèle jamais chargé ni interrogé** — trou confirmé, exactement comme
  décrit par le mandat.
- Ports natifs : `ss -tlnp` confirme `127.0.0.1:37821` occupé par le process natif (PID 905,
  toujours actif à ce jour) — non touché durant tout ce mandat, vérifié à nouveau après
  nettoyage final (voir Étape 9bis).
- Conteneurs tiers présents et non touchés (vérifié par `docker ps -a`, jamais stoppés/tués) :
  `agora-searxng` (8934), `flux-postgres` (5544), `bgutil-ytdlp-pot-provider` (4416).
- Aucun conteneur `echohub*` actif au démarrage de ce mandat. Volumes `echohub_echohub_models`
  et `echohub_echohub_userdata` (officiels, du `docker-compose.yml`) présents mais vides —
  non touchés, pas utilisés pour le test (volumes de test dédiés créés séparément, voir
  Étape 9).
- `PORTAGE-WINDOWS.md` recommande explicitement la **voie native Windows plutôt que Docker**
  pour la livraison finale (Partie 3, « Voie recommandée »), au motif de l'intégration desktop
  Tauri. Constat déjà noté et tranché par l'équipe précédente (voir note de cadrage en tête de
  ce fichier) : le mandat orchestrateur demande la brique Docker comme fondation indépendante,
  pas comme remplacement du plan natif. Je poursuis dans la même logique, sans redécouvrir ce
  débat.

## Étape 9 — Partie A : preuve d'inférence GPU réelle, bout en bout via l'API

Conteneur de test lancé sur ports alternatifs, volumes dédiés jetables (jamais les volumes
officiels du compose) :
```
docker run -d --name echohub-inftest --device=nvidia.com/gpu=all \
  -p 47820:80 -p 47821:37821 \
  -e MODELS_DIR=/data/models -e XDG_DATA_HOME=/data/user \
  -v echohub_inftest_models:/data/models -v echohub_inftest_userdata:/data/user \
  echohub:gpu
```
`curl http://127.0.0.1:47821/health` → `{"status":"ok",...}` après ~2 s. Logs de démarrage
identiques à ceux déjà validés par l'équipe précédente (DB initialisée sous `/data/user/...`).

**Modèle choisi** : `Qwen/Qwen2.5-0.5B-Instruct-GGUF`, fichier
`qwen2.5-0.5b-instruct-q4_k_m.gguf` — 0,5 milliard de paramètres, quantification Q4_K_M,
**491 400 032 octets (≈ 469 Mio)**. Choix motivé : dans la fourchette demandée (0,5–1,5 Md
paramètres), quantifié Q4, quelques centaines de Mo — respecte explicitement la contrainte
« ne jamais télécharger un modèle de plusieurs Go ».

Téléchargement **directement dans le conteneur** (`docker exec ... curl -fL -o
/data/models/qwen2.5-0.5b-instruct-q4_k_m.gguf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/...`)
→ `HTTP:200 SIZE:491400032`, dans le volume de test `echohub_inftest_models`.

**Chargement via l'API backend** (pas d'appel direct à la bibliothèque — la vraie chaîne
utilisateur) :
```
POST /inference/load
{"model_id":"qwen2.5-0.5b-instruct-q4_k_m",
 "gguf_path":"/data/models/qwen2.5-0.5b-instruct-q4_k_m.gguf",
 "n_gpu_layers":-1,"engine":"llama"}
```
→ `{"status":"loading",...}`, puis poll `GET /inference/load-state` jusqu'à
`loading_model_id:null, loaded_model_id:"qwen2.5-0.5b-instruct-q4_k_m"` (chargement terminé en
moins d'une seconde d'après les logs applicatifs : `[llama] Model loaded in 0.6s`).

**Preuve GPU — usage VRAM réel (mesure mécanique, pas une lecture de code)** :
`docker exec echohub-inftest nvidia-smi --query-compute-apps=pid,used_memory --format=csv` →
`52, 780 MiB` (PID 52 = le process uvicorn du conteneur). VRAM totale conteneur :
`2360 MiB` utilisés sur `12288 MiB` — cohérent avec un modèle 0,5 Md quantifié + contexte.

**Preuve GPU — couches offloadées, la preuve explicitement demandée par le mandat** :
`backend/services/llama_service.py:248` fixe `verbose=False` sur l'instance `Llama()` de
l'application — les logs natifs llama.cpp (`ggml_cuda_init`, `load_tensors: offloaded N/N`)
n'apparaissent donc jamais dans `docker logs` en usage normal (constat factuel sur le code,
non modifié — hors mandat). Pour obtenir la preuve textuelle exacte demandée sans toucher au
code applicatif, chargement diagnostique **du même fichier GGUF déjà présent dans le
conteneur**, en parallèle, via un appel direct `llama_cpp.Llama(..., verbose=True)` dans un
process Python jetable (`docker exec`), fermé aussitôt le log obtenu — ne remplace pas la
preuve API ci-dessus, la complète :
```
ggml_cuda_init: found 1 CUDA devices (Total VRAM: 11907 MiB):
  Device 0: NVIDIA GeForce RTX 3060, compute capability 8.6, VMM: yes, VRAM: 11907 MiB
llama_prepare_model_devices: using device CUDA0 (NVIDIA GeForce RTX 3060) (0000:07:00.0) - 9438 MiB free
print_info: n_layer               = 24
load_tensors: offloading output layer to GPU
load_tensors: offloading 23 repeating layers to GPU
load_tensors: offloaded 25/25 layers to GPU
load_tensors:        CUDA0 model buffer size =   373.73 MiB
CUDA : ARCHS = 860,1200 | FORCE_CUBLAS = 1 | USE_GRAPHS = 1 | ...
```
**25/25 couches (24 layers + output layer) offloadées sur CUDA0, ARCHS=860,1200 confirme que
le binaire compilé par l'équipe précédente contient bien sm_86 (build machine) et sm_120/120a
(cible RTX 5090), FORCE_CUBLAS=1 confirme le contournement du bug nvcc actif et fonctionnel.**

**Preuve de génération réelle de texte, via l'API `/inference/chat`** (chaîne utilisateur
complète, pas un appel bibliothèque) :
- Premier essai (prompt court, FR) : 7 tokens générés en 0,266 s — trop court pour une mesure
  fiable de débit (le modèle s'arrête tôt, `finish_reason:"stop"`), mais confirme déjà la
  génération : `"Cette phrase est un \"GPU."` (qualité de réponse faible, attendue d'un modèle
  0,5 Md quantifié Q4 en français — non représentatif, la preuve recherchée est la chaîne
  technique, pas la qualité du modèle).
- Second essai, prompt forçant une sortie longue (EN, `max_tokens:300`) :
  `usage.completion_tokens: 300`, `finish_reason:"length"`, texte cohérent en anglais sur
  l'histoire de l'informatique (qualité modeste mais texte réel, structuré, sur le bon sujet).
  **Temps mesuré côté client (`time curl`) : 3,601 s pour 300 tokens complétés.**

**Vitesse de génération mesurée : 300 tokens / 3,601 s ≈ 83,3 tokens/seconde**, sur RTX 3060
12 Go, modèle Qwen2.5-0.5B-Instruct Q4_K_M, `n_gpu_layers=-1` (offload complet), via l'API HTTP
complète (comprend donc la sérialisation JSON et l'aller-retour réseau loopback, pas seulement
le temps de calcul pur — c'est la mesure la plus honnête pour un point de comparaison
utilisateur final, à reproduire à l'identique sur la RTX 5090 quand la machine sera
disponible).

## Étape 9bis — Nettoyage post-validation

```
docker exec echohub-inftest curl -s -X POST http://127.0.0.1:37821/inference/unload
docker stop echohub-inftest && docker rm echohub-inftest
docker volume rm echohub_inftest_models echohub_inftest_userdata
```
Vérifié après coup (pas seulement supposé) : `docker ps -a` ne montre plus `echohub-inftest`,
`docker volume ls` ne montre plus `echohub_inftest_*` — modèle GGUF téléchargé supprimé avec le
volume (jamais copié hors du conteneur, jamais persisté ailleurs sur l'hôte). `ss -tlnp` reconfirme
`127.0.0.1:37821` toujours tenu par le PID natif d'origine (905) — instance native intacte,
conteneurs tiers (`agora-searxng`, `flux-postgres`, `bgutil-ytdlp-pot-provider`) jamais touchés.

**Critère d'arrêt Partie A atteint : texte réellement généré par un modèle chargé dans le
conteneur (via l'API backend, pas un appel bibliothèque isolé), couches GPU offloadées
confirmées textuellement (25/25 sur CUDA0), VRAM réellement consommée mesurée (780 MiB),
vitesse mesurée (≈ 83,3 tokens/s sur RTX 3060 pour ce modèle) consignée comme point de
comparaison pour la RTX 5090.**

## Étape 10 — Partie B : `start.ps1` / `stop.ps1`, entrée Windows en une commande

Recherche web avant choix (sources citées, pas de connaissance interne non vérifiée) :
- **Pilote NVIDIA minimal RTX 50 (Blackwell)** : 570.xx ou plus récent — confirmé, cohérent
  avec le constat déjà posé par `PORTAGE-WINDOWS.md`. Source :
  [leadergpu.com — Install NVIDIA drivers/CUDA for RTX 50 series](https://www.leadergpu.com/articles/616-install-nvidia-drivers-and-cuda-for-rtx-50-series).
- **Docker Desktop / WSL2** : le support GPU de Docker Desktop nécessite le moteur WSL2
  (pas Hyper-V classique), disponible depuis Docker Desktop 3.1+, WSL ≥ 1.1.3.0 pour le
  backend WSL2. Version actuelle constatée au moment de la rédaction : Docker Desktop
  4.83.0 (juillet 2026) — le script ne fige pas de version précise, il vérifie l'état
  fonctionnel réel (`docker info`, `OSType=linux`) plutôt qu'un numéro de version. Sources :
  [docs.docker.com — GPU support in Docker Desktop](https://docs.docker.com/desktop/features/gpu/),
  [docs.docker.com — Docker Desktop WSL2 backend](https://docs.docker.com/desktop/features/wsl/).
- **Règle critique pilote Windows-only** : déjà tranchée et sourcée par `PORTAGE-WINDOWS.md`
  (Partie 2) — le pilote NVIDIA Linux ne doit jamais être installé dans WSL2, seul le pilote
  Windows expose `libcuda.so` en stub côté Linux. Reprise telle quelle dans `start.ps1`
  (rappel affiché à l'utilisateur, pas de nouvelle recherche nécessaire, source déjà citée :
  [NVIDIA CUDA on WSL User Guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)).

**Fichiers produits** : `start.ps1` et `stop.ps1` (racine).

`start.ps1`, dans l'ordre : (1) `docker` présent + `docker info` répond → sinon lien direct
vers Docker Desktop ; (2) moteur WSL2 actif (`docker info --format '{{.OSType}}'` = `linux`
+ `wsl.exe --status`) → sinon lien vers `wsl --install` ; (3) `nvidia-smi.exe` (côté Windows)
détecte un GPU, avertissement si version pilote < 570 ; rappel critique Windows-only/jamais
de pilote Linux dans WSL2 affiché explicitement ; (4) test réel `docker run --rm --gpus all
nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi` (GPU réellement exposable à un conteneur,
pas juste visible sur l'hôte) ; (5) build de `echohub:gpu` si absente (`docker image
inspect`) ; (6) `docker compose up -d` ; (7) **attente réelle** du point de santé
`http://localhost:37821/health` par polling (`Invoke-WebRequest`, intervalle 2 s, boucle
bornée par `$HealthTimeoutSeconds` = 180 s par défaut, jamais un `Start-Sleep` fixe non
vérifié) avec message d'erreur actionnable (`docker compose logs -f`) si le délai est
atteint ; (8) ouverture du navigateur sur `http://localhost:37820`. Chaque échec de
vérification affiche la cause et un lien officiel exact, jamais un message générique.

`stop.ps1` : symétrique et minimal — `docker compose down`, volumes conservés (modèles/
données utilisateur), rappel de la commande de redémarrage.

**Vérification mécanique réelle du script** (pas seulement une relecture) : `pwsh` absent de
cette machine (Arch Linux, confirmé par `which pwsh` négatif) — décision prise de ne pas
l'installer sur l'hôte (hors mandat, modification système non demandée). Alternative
mécanique trouvée : conteneur officiel `mcr.microsoft.com/powershell:latest` (Microsoft),
lancé une fois via Docker, appelant directement le parser PowerShell
(`[System.Management.Automation.Language.Parser]::ParseFile`) sur les deux fichiers montés
en lecture seule :
```
start.ps1: OK, aucune erreur de syntaxe
stop.ps1: OK, aucune erreur de syntaxe
```
Image `mcr.microsoft.com/powershell:latest` supprimée après usage (`docker rmi`) — aucun
résidu. **Ce test valide la syntaxe PowerShell réelle (parsing), pas le comportement runtime
sur Windows** (accès à `nvidia-smi.exe`, `wsl.exe`, Docker Desktop réel — tout ceci reste non
testé, aucune machine Windows disponible ici). Limite assumée et documentée dans le
README (Partie C).

## Étape 11 — Partie C : documentation

`README.md` mis à jour — voir section « Windows » ajoutée, remplace la ligne « Linux, macOS,
or Windows (WSL2) » non étayée par une affirmation précise de ce qui existe réellement
(scripts + image, non testés sur RTX 5090). Détail dans le diff du fichier, pas reproduit ici.

## Étape 12 — Partie D : exécution réelle de `start.ps1` / `stop.ps1` (équipe de suite)

Mandat : la validation précédente (Étape 10) ne prouvait que le *parsing* syntaxique
(`[System.Management.Automation.Language.Parser]::ParseFile`, moteur PS 7 du conteneur).
Aucune exécution réelle n'avait eu lieu, et le parseur PS7 ne peut par construction pas
détecter une incompatibilité avec Windows PowerShell 5.1 (le moteur par défaut sur tout
Windows non modifié) : il analyse avec la grammaire 7, pas 5.1. Cette étape corrige ce trou
en exécutant réellement les scripts, dans un conteneur `mcr.microsoft.com/powershell:latest`
jetable (supprimé après usage), sur trois scénarios : à vide, à vide avec faux
`docker`/`wsl.exe`/`nvidia-smi.exe` simulant un poste équipé, et le même chemin avec le point
de santé qui ne répond jamais.

### Q1 — Compatibilité PowerShell 5.1 et politique d'exécution

**Syntaxe** : balayage exhaustif des deux fichiers pour tout ce qui n'existe qu'en PS7+
(opérateur ternaire `? :`, `??`, `?.`, chaînage de pipeline `&&`/`||`, `Test-Json`,
`ForEach-Object -Parallel`, `$PSStyle`) — recherche par grep ciblée, zéro occurrence. Les
constructions utilisées (`$PSScriptRoot`, `[CmdletBinding()]`, `*> $null`,
`Invoke-WebRequest -UseBasicParsing`, sous-expressions `$(...)`, `-match`/`$Matches`) sont
toutes disponibles depuis PowerShell 3.0–5.0 au plus tard. **Aucune incompatibilité de
syntaxe trouvée.**

**Défaut réel trouvé et corrigé — encodage sans BOM.** Les deux fichiers étaient en UTF-8
**sans BOM** (confirmé : `file` → `UTF-8 text` sans mention BOM ; premier octet `23 52` = `#R`,
pas `EF BB BF`). Les deux scripts contiennent des caractères non-ASCII dans les messages
affichés à l'utilisateur (`—`, `─`, `▶`, `⚠`). Windows PowerShell 5.1 n'a pas de détection
UTF-8 automatique sans BOM : il lit un `.ps1` sans BOM avec la page de code ANSI système
(souvent Windows-1252 sur un poste FR), ce qui corrompt ces caractères à l'affichage
(mojibake) — pas une erreur bloquante, mais un message d'erreur illisible à l'endroit précis
où le script doit guider l'utilisateur. Source :
[PowerShell: Encoding — renenyffenegger.ch](https://renenyffenegger.ch/notes/Windows/PowerShell/encoding/index),
confirmée par la documentation officielle
[about_Character_Encoding (PowerShell 5.1)](https://github.com/MicrosoftDocs/PowerShell-Docs/blob/main/reference/5.1/Microsoft.PowerShell.Core/About/about_Character_Encoding.md).
**Corrigé** : BOM UTF-8 (`EF BB BF`) ajouté en tête des deux fichiers — solution recommandée
par Microsoft pour ce cas exact. Reparsing PS7 revérifié après coup : 0 erreur sur les deux
fichiers.

**Politique d'exécution — le vrai blocage.** Sur une installation Windows 11 standard,
`Get-ExecutionPolicy` vaut `Restricted` par défaut pour tout compte utilisateur (aucune
politique définie nulle part) : **tout** script `.ps1` non signé est refusé, y compris celui-ci.
Source : [about_Execution_Policies (Microsoft Learn)](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies).
Taper `.\start.ps1` dans un PowerShell fraîchement ouvert produit :
```
.\start.ps1 : File ...\start.ps1 cannot be loaded because running scripts is disabled
on this system. For more information, see about_Execution_Policies at
https://go.microsoft.com/fwlink/?LinkID=135170.
```
`git clone` ne pose pas de Mark-of-the-Web (MOTW ne s'applique qu'aux fichiers téléchargés
via navigateur/store, pas à un clone git) donc ce n'est pas un blocage MOTW — c'est la
politique d'exécution elle-même. Vérifié aussi : le menu contextuel natif Windows
« Exécuter avec PowerShell » sur un `.ps1` invoque en réalité
`powershell.exe -ExecutionPolicy Bypass -File "%1"` (ou l'équivalent `Set-ExecutionPolicy
-Scope Process Bypass`), donc **ce geste précis contourne le blocage sans rien changer de
permanent**. Source : [What's behind "Run with PowerShell" context menu? — p0w3rsh3ll](https://p0w3rsh3ll.wordpress.com/2016/07/19/whats-behind-run-with-powershell-context-menu/).
**Conclusion : la promesse « une seule commande, `.\start.ps1` tout court » du README était
fausse pour un poste vierge.** README corrigé (section Windows, « One command ») pour dire la
vérité : clic droit > Exécuter avec PowerShell (fonctionne sans rien changer), ou
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` une fois, ou
`powershell -ExecutionPolicy Bypass -File .\start.ps1`.

### Q2 — Comportement à vide (aucun logiciel installé)

Exécution réelle de `start.ps1` dans le conteneur PowerShell, PATH ne contenant ni `docker`
ni `wsl.exe` ni `nvidia-smi.exe`. Sortie exacte vue par l'utilisateur :
```
EchoHub — demarrage (Docker Desktop / WSL2 / GPU NVIDIA)
─────────────────────────────────────────────────────────

▶ Docker Desktop
  [X]  Docker n'est pas installe (commande 'docker' introuvable).
       Installe Docker Desktop pour Windows (inclut le moteur WSL2) :
       https://www.docker.com/products/docker-desktop/
       Redemarre ce script apres l'installation et le premier lancement de Docker Desktop.
```
Code de sortie 1, arrêt immédiat et propre — aucune trace d'exception, message actionnable
avec lien officiel. `stop.ps1` dans les mêmes conditions : message clair
(« Docker n'est pas installe ... — rien a arreter. »), exit 1, pareillement propre.
**Aucun défaut : comportement exactement conforme à l'attendu.**

### Q3 — Chemin nominal (faux `docker`/`wsl.exe`/`nvidia-smi.exe` dans le PATH)

Trois faux exécutables bash (`docker`, `wsl.exe`, `nvidia-smi.exe`) écrits pour répondre
comme les vrais le feraient sur un poste équipé (`docker info --format '{{.OSType}}'` →
`linux`, `wsl.exe --status` → exit 0, `nvidia-smi.exe --query-gpu=...` →
`NVIDIA GeForce RTX 5090, 576.02`, `docker image inspect` → image déjà présente,
`docker compose up/down` → exit 0). Deux scénarios pour le point de santé :

- **Le backend répond** (petit serveur `HttpListener` PowerShell en tâche de fond sur le port
  37821) : `start.ps1` enchaîne ses 7 étapes dans l'ordre exact du code — Docker Desktop →
  WSL2 → GPU → build (sauté, image déjà présente) → `compose up -d` → attente polling
  (`[OK] Backend pret ... repond 200`, revenu bien avant le timeout de 30 s fixé pour le
  test) → ouverture navigateur. Exit code 0.
- **Le backend ne répond jamais** (aucun listener démarré, `-HealthTimeoutSeconds 6`/`8` pour
  ne pas attendre les 180 s réelles) : la boucle de polling est correctement bornée — mesuré
  à `real 0m6.583s` / `0m8.589s` pour des timeouts de 6 s/8 s (pas de blocage indéfini),
  message final clair (« Le backend ne repond toujours pas ... apres Ns »,
  `docker compose logs -f`, cause probable), exit code 1. **Aucun risque d'attente infinie.**

**Défaut réel trouvé et corrigé — ouverture du navigateur sans filet.** `Start-Process
$webUrl` (ligne 199 d'origine) est la façon standard et correcte d'ouvrir l'URL dans le
navigateur par défaut sur Windows (`ShellExecute` sous le capot) — source :
[Opening URLs in Different Browsers Using PowerShell](https://powershellprodigy.wordpress.com/2024/10/07/opening-urls-in-different-browsers-using-powershell/).
Mais c'était le **seul** appel du script sans `try/catch`, alors que `$ErrorActionPreference
= 'Stop'` est actif globalement et que chaque autre étape a son `Exit-WithGuidance` dédié.
Reproduit dans le conteneur (pas d'association shell pour les URL sous Linux — échec attendu
et normal ici, pas un signal de bug côté Windows) : le script plantait avec une trace
d'exception PowerShell brute **après avoir réussi toutes les étapes précédentes**
(conteneurs démarrés, backend sain) — l'utilisateur aurait vu une erreur rouge illisible à la
toute dernière étape alors qu'EchoHub tournait déjà correctement.
**Corrigé** : `try/catch` ajouté autour de `Start-Process $webUrl` ; en cas d'échec (pas de
navigateur par défaut configuré, ou autre erreur `ShellExecute`), le script avertit
(`Write-Warn`) et donne l'URL à ouvrir manuellement, au lieu de planter — le script se termine
alors avec un code de sortie 0 puisqu'EchoHub est réellement opérationnel. Revérifié après
correction : le warning s'affiche proprement, le script se termine bien en exit 0.

`stop.ps1` chemin nominal : `docker compose down` (faux) → `[OK] Conteneurs arretes. Volumes
... conserves.` → exit 0. Conforme, rien à corriger.

### Fichiers modifiés dans cette étape

- `start.ps1` : BOM UTF-8 ajouté ; `try/catch` ajouté autour de l'ouverture du navigateur.
- `stop.ps1` : BOM UTF-8 ajouté (aucun autre changement — script déjà correct).
- `README.md` (section Windows, « One command ») : documente la vraie procédure
  (`Restricted` par défaut, trois façons de contourner, clic droit recommandé).

Toutes les corrections revérifiées par une nouvelle exécution réelle après application
(voir sorties ci-dessus) — pas seulement relues.

### Verdict — trois lignes

Cloné tel quel sur Windows 11, `.\start.ps1` tapé dans un terminal PowerShell classique
**sera bloqué avant Docker** par `Restricted` (politique d'exécution par défaut) : il faut
un clic droit « Exécuter avec PowerShell » (marche sans rien changer), ou activer une fois
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Une fois ce geste fait, la logique du
script elle-même est saine : compatible PowerShell 5.1, échoue proprement et clairement si
Docker/WSL2/GPU manquent, enchaîne ses étapes dans le bon ordre, attend le backend sans
jamais bloquer indéfiniment, et n'écrase plus d'exception brute si le navigateur ne s'ouvre
pas tout seul. Le seul point encore non vérifiable ici faute de machine Windows/RTX 5090 :
que Docker Desktop, WSL2 et le pilote NVIDIA réels répondent exactement comme les simulations
utilisées pour ce test.

---

# Journal — équipe validation interface web (ccremote), 2026-08-09

Équipe de suite. Mandat : valider l'interface web elle-même dans le conteneur — affichage réel,
navigation, conversation complète de bout en bout via un navigateur automatisé (Playwright). Les
mandats précédents avaient validé le build, le GPU, et une conversation via appel API direct
(`/inference/chat`) — jamais via l'écran de chat effectivement rendu au navigateur. C'est ce trou
précis que ce mandat comble.

## Étape 13 — État des lieux

- Aucun conteneur `echohub*` actif, ports 47820/47821 libres, instance native intacte sur
  37821 (PID 905, non touchée), conteneurs tiers (`agora-searxng`, `flux-postgres`,
  `bgutil-ytdlp-pot-provider`) non touchés — revérifié avant et après ce mandat.
- Conteneur de test lancé : `echohub-uitest`, volumes dédiés `echohub_uitest_models` /
  `echohub_uitest_userdata`, mêmes ports alternatifs 47820/47821 déjà utilisés par les mandats
  précédents. `docker exec ... nvidia-smi` et `/health` revalidés sains avant de commencer
  (rien de nouveau par rapport aux étapes précédentes, non répété en détail ici).

## Étape 14 — Premier lancement réel dans un navigateur (Playwright, Chromium headless)

Contrairement aux mandats précédents qui n'avaient jamais ouvert l'interface dans un navigateur,
ce conteneur n'a **jamais** été configuré via l'application — premier démarrage réel. L'app
affiche donc son propre assistant de configuration (`InstallerApp.tsx`), pas directement l'écran
de chat. Capture `logs/screenshots/01_accueil.png` : écran « Welcome to EchoHub » bien rendu,
sombre, cohérent, aucune erreur console/réseau.

**Décision prise sans redemander** : l'étape 2 de ce wizard (« Storage locations ») mène à un
bouton « Install now » qui, d'après lecture du code (`backend/routers/installer.py`), déclenche
l'installation de **vLLM 0.21.0 (~4 Go de téléchargement, 10-30 min)** dès qu'un GPU NVIDIA est
détecté — ce que le conteneur de test a bien. Interdit absolu du mandat : jamais plus d'1 Go
téléchargé. Contournement légitime retenu, sans modification de code : appel direct de
`POST /installer/complete` (endpoint déjà exposé par l'application elle-même, prévu pour marquer
l'installation terminée) pour sauter cette étape. Le moteur d'inférence réellement testé plus
bas (llama.cpp/GGUF) n'a jamais eu besoin de vLLM — ce contournement ne retire rien au test
décisif demandé.

Après rechargement, l'app affiche un onboarding produit en 6 étapes (bienvenue, stockage,
matériel détecté, moteurs d'inférence, compatibilité modèles, écran final) — toutes parcourues
et capturées (`02` à `09_app_shell.png`), toutes bien rendues, aucune erreur console/réseau.
Point à noter, positif : l'étape 3/6 « Your hardware » détecte et affiche correctement
**« NVIDIA GeForce RTX 3060, 12 GB VRAM »** — preuve supplémentaire, côté interface cette fois
(pas seulement `nvidia-smi` en `docker exec`), que le GPU est bien exposé au conteneur et lu par
l'application elle-même.

Écran de chat principal (`09_app_shell.png`) : shell complet bien rendu — liste de
conversations, sélecteur de modèle (« No model loaded »), panneau de droite (Profile, System
Prompt, Permanent Rules, Parameters, Skills), zone de saisie « Load a model to start chatting »,
indicateur GPU en bas de la barre latérale. Aucune erreur console. Une seule requête réseau en
échec relevée en boucle sur chaque capture : `GET /api/models/downloads/stream` →
`net::ERR_ABORTED` — investiguée plus loin (étape 15), pas un souci de streaming en soi (voir
verdict).

## Étape 15 — Écran Discover : recherche et fiche modèle

`logs/screenshots/10_discover.png` : grille de modèles réelle interrogée en direct sur
Hugging Face Hub à travers le proxy nginx (`/api/models/search` → backend → HF Hub), 20
résultats avec badges de format/taille VRAM estimée, aucune erreur. Recherche
« Qwen2.5-0.5B-Instruct-GGUF » (`11_search_qwen05b.png`) retourne des résultats cohérents.
Fiche modèle ouverte (`12_fiche_modele.png`, `13_apres_clic_variant.png`) : panneau détaillé
correct — variantes de quantification, tailles, description README, avertissement de
compatibilité (normal, aucun moteur vLLM installé, cohérent avec le choix de l'étape 13).

**Modèle retenu pour le test décisif** : `jc-builds/Qwen2.5-0.5B-Instruct-Q4_K_M-GGUF` — 0,5 Md
de paramètres, quantification Q4_K_M, **0,37 Go** annoncés (confirmé après coup : 397 807 936
octets réels ≈ 0,37 Gio) — dans la fourchette demandée, très en dessous de la limite d'1 Go.

## Étape 16 — Défaut réel découvert : le modèle téléchargé via l'interface est invisible dans la bibliothèque

Téléchargement lancé depuis l'interface (bouton « Download », capture `15_download_lance.png` :
barre de progression réelle affichée, 0 % → en cours). Backend confirme dans ses logs :
```
2026-08-09 17:18:06 | INFO | download_manager:start_download:164 - Download started: jc-builds/Qwen2.5-0.5B-Instruct-Q4_K_M-GGUF
2026-08-09 17:18:12 | INFO | download_manager:_run_download:107 - Download complete: jc-builds/Qwen2.5-0.5B-Instruct-Q4_K_M-GGUF (0.37 GB)
```
Le flux SSE `/models/downloads/stream` confirme aussi côté client, via `curl` direct sur le
proxy : `state: complete, downloaded_gb: 0.37, total_gb: 0.37`. **Mais** `GET /models/downloaded`
retourne `[]` en boucle après coup, et l'écran « My Models »/bibliothèque de l'interface
n'affiche jamais le modèle comme disponible.

**Cause établie sur artefact réel (pas une lecture de code seule)** : `docker exec` confirme le
fichier bien présent sur disque, taille correcte, à
`/mnt/models/echohub/jc-builds--Qwen2.5-0.5B-Instruct-Q4_K_M-GGUF/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf`
— **pas** dans `/data/models` (le volume monté, `MODELS_DIR=/data/models` fourni en variable
d'environnement au conteneur). `curl http://127.0.0.1:37821/settings/paths` confirme :
`{"models_dir":"/mnt/models/echohub","models_dir_is_default":true}`.

Lecture du code (`backend/services/hf_service.py`, `backend/services/config_service.py`) :
**deux définitions différentes et incohérentes du dossier des modèles dans la même codebase** :
- `hf_service.py:18` — `MODELS_DIR = Path(os.getenv("MODELS_DIR", "/mnt/models/echohub"))`,
  constante figée une fois pour toutes au chargement du module. Dans ce conteneur, vaut donc
  `/data/models` (la variable d'env est bien lue). **Utilisée par `list_downloaded()`**, donc par
  `GET /models/downloaded` — ce qui explique la liste vide, `/data/models` étant réellement vide.
- `hf_service.py:8-15` (`_get_models_dir()`) délègue à `config_service.get_models_dir()`, dont le
  défaut (`config_service.py:19`) est **codé en dur** à `"/mnt/models/echohub"`, sans jamais lire
  `os.getenv("MODELS_DIR")`. **Utilisée pour le téléchargement réel** (`_model_dir()`, appelée par
  le download manager) — d'où l'écriture au mauvais endroit.

**Conclusion sur la nature du défaut, conforme au mandat (ne pas corriger le code
applicatif)** : ce n'est pas un problème de configuration du conteneur — la variable d'env
`MODELS_DIR=/data/models` est correctement transmise et correctement lue par au moins un des deux
chemins de code. C'est une incohérence interne au code Python applicatif (deux sources de vérité
pour le même réglage, l'une respectant la variable d'environnement, l'autre l'ignorant
totalement) — **non corrigée**, signalée ici avec fichiers et lignes exactes pour l'équipe qui
travaille le code en parallèle. Cela affecte potentiellement aussi l'installation native (hors
Docker) dès qu'un opérateur positionne `MODELS_DIR` en variable d'environnement système sans
passer par l'assistant d'installation.

**Contournement appliqué pour poursuivre le test d'interface, sans modifier une ligne de code** :
`POST /settings/paths/models-dir {"path":"/data/models"}` (endpoint déjà exposé par
l'application, celui-là même que l'assistant d'installation officiel appelle à l'étape
« Storage locations » si l'utilisateur y confirme un chemin) pour aligner `config_service` sur
la variable d'environnement du conteneur, puis déplacement du dossier déjà téléchargé de
`/mnt/models/echohub/...` vers `/data/models/...` (mêmes octets, aucun nouveau téléchargement).

L'appel POST a déclenché une migration asynchrone (`{"status":"migration_pending", ...
"files_total":0}`, source déjà vidée par mon déplacement manuel) qui n'a **pas** mis à jour
`config_service.get_models_dir()` (`GET /settings/paths` continue de répondre
`/mnt/models/echohub`, `models_dir_is_default:true`) — troisième indice du même défaut, pas
creusé plus loin, hors mandat. Pour couvrir les deux résolutions de chemin coexistant dans le
code (`hf_service._get_models_dir()`/`config_service`, utilisée pour charger un modèle ;
`hf_service.MODELS_DIR`, utilisée pour lister), un lien symbolique
`/mnt/models/echohub/jc-builds--...` → `/data/models/jc-builds--...` a été créé (aucune
duplication de données, aucun nouveau téléchargement).

## Étape 17 — Écran « My Models » : le modèle apparaît, se charge, preuve GPU via l'interface

`logs/screenshots/17_my_models.png` : après le contournement, le modèle apparaît correctement
— « Qwen2.5-0.5B-Instruct-Q4_K_M-GGUF », statut `downloaded`, 0,28 GB VRAM estimée, bouton
« Load ». Clic sur « Load » → modale de configuration de chargement très complète
(`18_load_click.png`) : **monitoring matériel en direct affiché dans l'interface elle-même**
(RTX 3060 51 °C, 1,5/12 GB VRAM, 3 % d'utilisation ; CPU 46,6 °C, 8,8/47 GB RAM) — preuve
supplémentaire, cette fois explicitement dans l'écran destiné à l'utilisateur, que le GPU est
lu correctement depuis l'intérieur du conteneur. Profil « Performance » (GPU complet)
sélectionné par défaut, confirmé par clic sur « Load model ».

Vérification mécanique côté API après clic (le rendu visuel de la liste n'avait pas encore
rafraîchi son badge au moment de la capture, non bloquant) :
```
GET /inference/load-state → {"loading_model_id":null,
  "loaded_model_id":"jc-builds/Qwen2.5-0.5B-Instruct-Q4_K_M-GGUF", "engine":"llama",
  "load_config":{"n_gpu_layers":-1, "gguf_path":"/mnt/models/echohub/jc-builds--.../....gguf", ...}}
```
`gguf_path` résolu via le lien symbolique — confirme que le chargement passe bien par
`config_service.get_models_dir()` (pas la variable d'env), cohérent avec l'analyse de
l'étape 15.

## Étape 18 — Conversation complète dans l'écran de chat, capture regardée réellement

Navigation vers l'onglet Chat (`20_chat_model_loaded.png`) : en-tête confirme
« Qwen2.5-0.5B-Instruct-Q4_K… », badge vert « loaded », « llama.cpp », « Q4_K_M ». Champ de
saisie actif (« Load a model to start chatting » a disparu, remplacé par « Message... »).

**Premier message envoyé depuis l'interface** : « Explique en 3 phrases ce qu'est un GPU. »
**Réponse affichée à l'écran** (`21_chat_streaming_t0.png`, regardée réellement, pas déduite) :
« Hi, how can I assist you today? » — réponse hors-sujet mais bien réelle, texte rendu dans la
bulle de conversation, métriques réelles affichées sous la bulle : **9 tokens, 138.5 tok/s,
137 ms TTFT, 0,27 s total, moteur llama**. Qualité de réponse faible (modèle 0,5 Md, attendu,
déjà observé par le mandat précédent en test API direct).

**Second message, prompt conçu pour forcer une réponse longue** : « Write a long detailed
paragraph (at least 150 words) about the history of computers. » **Réponse complète affichée**
(`22_streaming_a.png`/`23_streaming_b.png`, identiques — génération déjà terminée avant les deux
captures espacées de plusieurs secondes, le modèle étant trop rapide pour ce volume de texte) :
10 paragraphes courts, texte cohérent en anglais, factuellement peu fiable (« John Gottlieb »,
« EDS-1 » n'existent pas — hallucinations attendues d'un modèle 0,5 Md, non représentatif de la
qualité, la preuve recherchée est la chaîne technique). Métriques : **286 tokens, 160,8 tok/s,
27 ms TTFT, 1,83 s total**.

**Preuve du streaming progressif, indépendante du timing des captures d'écran** : les deux
captures consécutives étant identiques (génération plus rapide que l'intervalle entre deux
appels d'outil MCP), preuve obtenue directement au niveau réseau via `curl -N` sur
`/inference/chat` (SSE, à travers le proxy nginx du conteneur, pas un accès direct backend) :
```
19:26:17 data: {"choices":[{"delta":{"content":"To"}, ...}]}
19:26:17 data: {"choices":[{"delta":{"content":" count"}, ...}]}
19:26:17 data: {"choices":[{"delta":{"content":" from"}, ...}]}
...
19:26:18 data: {"choices":[{"delta":{"content":" each"}, ...}]}
```
Chaque événement SSE transporte un seul mot/token, et le flux s'étale sur plusieurs secondes
d'horloge réelle (17 → 18, sur une requête à 250 tokens max) — **la mise en tampon nginx est
bien désactivée pour ce endpoint dans ce conteneur** (`proxy_buffering off`, confirmé en
pratique, pas seulement dans le fichier de config). Le token n'arrive pas d'un bloc à la fin.

## Étape 19 — Nettoyage final

```
docker exec echohub-uitest curl -s -X POST http://127.0.0.1:37821/inference/unload
docker stop echohub-uitest && docker rm echohub-uitest
docker volume rm echohub_uitest_models echohub_uitest_userdata
```
Vérifié après coup : `docker ps -a` ne montre plus `echohub-uitest`, `docker volume ls` ne
montre plus `echohub_uitest_*` (donc le fichier GGUF téléchargé, quel que soit son emplacement
réel sur la couche writable du conteneur ou le volume, a disparu avec le conteneur). `ss -tlnp`
reconfirme `127.0.0.1:37821` toujours tenu par le PID natif d'origine (905). `docker ps`
reconfirme `agora-searxng`, `flux-postgres`, `bgutil-pot` toujours actifs, jamais touchés.
Navigateur Playwright fermé proprement.

## Conclusion de ce mandat (validation interface web)

**Critère d'arrêt atteint : une conversation complète a eu lieu dans l'interface servie par le
conteneur** — modèle téléchargé depuis l'écran Discover, chargé depuis l'écran My Models,
message envoyé depuis l'écran Chat, réponse affichée à l'écran et regardée réellement sur
capture, streaming progressif confirmé au niveau réseau. Zéro erreur console JavaScript sur les
9 écrans capturés. Une seule requête réseau en échec relevée en boucle
(`GET /api/models/downloads/stream` → `net::ERR_ABORTED`) — investiguée : le endpoint répond
`200 OK` et un flux SSE valide quand interrogé directement (`curl`), donc **pas un défaut du
proxy ou du endpoint** ; le plus probable est un flux SSE laissé ouvert par un composant React
(écran Discover ou My Models) coupé (`AbortController`/démontage de composant) à chaque
changement d'écran pendant la session Playwright — comportement visible aussi en usage normal
au clic rapide entre onglets, non creusé plus loin (hors mandat, pas bloquant pour le parcours).

**Un vrai défaut d'interface a été trouvé et documenté avec cause exacte (étape 15)** :
un modèle téléchargé depuis l'écran Discover n'apparaît **jamais** dans la bibliothèque
(« My Models ») ni dans le sélecteur de modèle, tant que l'utilisateur n'a pas explicitement
confirmé un chemin de stockage via l'assistant d'installation ou l'écran Settings → Paths — la
variable d'environnement `MODELS_DIR` du conteneur, bien que correctement transmise et lue par
une partie du code, est ignorée par `config_service.py` (défaut codé en dur), qui est la partie
du code utilisée pour l'écriture réelle du fichier téléchargé. **Sur ce conteneur précis, avec
la configuration `docker-compose.yml` actuelle (ports 37820/37821, volumes propres, jamais
démarré une première fois avec confirmation manuelle du chemin), un utilisateur qui suit le
parcours normal (assistant d'installation → Discover → Download → My Models → Load) rencontrera
ce défaut au premier lancement**, sauf s'il modifie le chemin par défaut proposé à l'étape
« Storage locations » du wizard pour qu'il corresponde à celui réellement monté en volume — ce
que rien dans l'interface ne l'invite à faire (le champ affiche `/mnt/models/echohub` comme
valeur déjà correcte, sans lien visible avec le volume Docker). Fichiers et lignes exactes :
`backend/services/hf_service.py:8-18`, `backend/services/config_service.py:19`. **Non corrigé**,
conformément au mandat — signalé pour l'équipe qui travaille le code applicatif en parallèle.

**Hors du strict test décisif, tout le reste de l'interface est fonctionnel et bien rendu** :
assistant d'installation (6+2 écrans), écran Discover (recherche Hugging Face en direct à
travers le proxy), fiche modèle détaillée, modale de chargement avec monitoring GPU/CPU en
direct, écran de chat complet (system prompt, permanent rules, paramètres d'inférence,
compétences). Aucune page blanche, aucun écran d'erreur, aucune interface à moitié chargée
observée sur les 9 écrans capturés et lus réellement.

**Verdict : l'application est utilisable de bout en bout dans le conteneur**, à la condition —
non automatique au premier lancement — que le chemin de stockage des modèles soit explicitement
confirmé une fois (via l'assistant d'installation ou Settings → Paths) pour correspondre au
volume Docker monté. Sans cette étape manuelle, l'utilisateur télécharge un modèle qui semble
réussir (barre de progression à 100 %, log backend « Download complete ») mais reste ensuite
introuvable dans sa propre bibliothèque — un piège silencieux, sans message d'erreur, que
l'équipe suivante devrait considérer prioritaire.

**Captures archivées** (`logs/screenshots/`, préfixées par ordre chronologique 01 à 23) :
accueil installeur, storage locations, app principale post-bypass, onboarding produit (6
écrans), shell de chat vide, Discover, recherche, fiche modèle (2 captures), progression de
téléchargement, My Models avant/après chargement, modale de chargement, chat avec modèle chargé,
deux réponses de chat (courte et longue).

---

# Journal — équipe installation Windows automatique (ccremote), 2026-08-09

Mandat : produire `setup-windows.ps1` pour qu'un poste Windows 11 neuf n'ait presque rien à
faire — élévation admin auto, installation de ce qui manque (WSL2, une distribution Linux,
Docker Desktop), vérification du pilote NVIDIA, reprise automatique après le redémarrage
imposé par WSL2, puis lancement de `start.ps1`.

## Étape 20 — Recherche avant écriture (sources citées dans le script et le README)

- **`wsl --install`** : active les fonctionnalités optionnelles Windows requises
  (`Microsoft-Windows-Subsystem-Linux`, `VirtualMachinePlatform`), installe le noyau WSL2 et,
  sans `--no-distribution`, une distribution par défaut (Ubuntu) ; un redémarrage est
  nécessaire la première fois sur une machine non modifiée, car l'activation de
  fonctionnalités optionnelles Windows l'exige structurellement. Source :
  [Install WSL — Microsoft Learn](https://learn.microsoft.com/en-us/windows/wsl/install).
- **Docker Desktop via winget** : id de paquet `Docker.DockerDesktop`, installation
  silencieuse `winget install --id Docker.DockerDesktop --exact --silent
  --accept-package-agreements --accept-source-agreements`. Alternative directe (installeur
  seul) : `Docker Desktop Installer.exe install --quiet --accept-license --backend=wsl-2`.
  Sources : [issue microsoft/winget-pkgs #45705](https://github.com/microsoft/winget-pkgs/issues/45705),
  [wingetly.io — Docker Desktop silent install](https://www.wingetly.io/apps/docker/docker-desktop/silent-install).
- **Pilote NVIDIA minimal Blackwell (RTX 50/5090)** : 570.xx ou plus récent — confirmé,
  cohérent avec ce que Étape 10 avait déjà établi. Sources :
  [leadergpu.com — Install NVIDIA drivers/CUDA for RTX 50 series](https://www.leadergpu.com/articles/616-install-nvidia-drivers-and-cuda-for-rtx-50-series),
  [NVIDIA CUDA on WSL User Guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).
- **Mécanisme de reprise après redémarrage** : tâche planifiée (`schtasks /SC ONLOGON
  /RL HIGHEST`) plutôt qu'une clé de registre `RunOnce`. Deux raisons : (1) Docker Desktop
  est une application graphique qui a besoin d'une session utilisateur interactive pour
  démarrer — une entrée `HKLM\...\RunOnce` s'exécute en tant que SYSTEM avant l'ouverture de
  session et ne peut pas la lancer, alors qu'`ONLOGON` s'exécute bien dans la session de
  l'utilisateur qui se reconnecte ; (2) une tâche planifiée nommée reste visible et
  supprimable (`Get-ScheduledTask`/`schtasks /Query`), alors que `RunOnce` est un motif que
  des AV/EDR traitent parfois comme suspect et purgent seuls. Aucune connexion automatique
  (autologon) n'a été configurée — stocker un mot de passe en clair dans le registre pour
  l'éviter aurait été un risque de sécurité largement disproportionné par rapport au confort
  gagné ; l'utilisateur rouvre sa session normalement et `ONLOGON` reprend à ce moment précis.
  Sources : [Continuing PowerShell Scripts After Reboot](https://www.advancedinstaller.com/continue-powershell-script-after-reboot.html),
  [Automatically resuming PowerShell Workflow jobs at logon — PowerShell Team](https://devblogs.microsoft.com/powershell/automatically-resuming-windows-powershell-workflow-jobs-at-logon/).

## Étape 21 — Vérification mécanique (conteneur PowerShell jetable, comme l'Étape 10)

Même méthode que l'équipe précédente : aucune machine Windows disponible ici non plus.
`mcr.microsoft.com/powershell:latest` lancé via Docker, supprimé après usage.

**Parsing** : `[System.Management.Automation.Language.Parser]::ParseFile` sur
`setup-windows.ps1` → 0 erreur de syntaxe. Balayage grep pour les constructions PS7+
(`??`, `?.`, `&&`, `||`, `Test-Json`, `ForEach-Object -Parallel`, `$PSStyle`, opérateur
ternaire) → zéro occurrence, comme pour `start.ps1`/`stop.ps1`.

**Exécution réelle, trois scénarios**, avec de faux `wsl.exe`/`docker.exe`/`nvidia-smi.exe`/
`winget.exe`/`schtasks.exe` dans le `PATH` du conteneur (les deux appels à des API
Windows-only — `WindowsPrincipal` pour l'élévation, `Restart-Computer` — ont dû être
neutralisés dans une copie de test uniquement, ces types n'existant pas sous PowerShell sur
Linux ; le fichier réel commité n'est pas modifié) :

1. **Tout déjà présent** (WSL2 + distribution + Docker Desktop) : le script détecte chaque
   composant présent, saute son installation, attend Docker (bornage `-DockerReadyTimeoutSeconds`,
   testé à 10 s), puis enchaîne correctement sur `start.ps1`, qui lui-même déroule ses 7 étapes
   jusqu'au timeout attendu du point de santé (aucun backend réel dans ce conteneur — signature
   identique à la validation de l'Étape 10). Chaînage `setup-windows.ps1` → `start.ps1` confirmé.
2. **WSL2 absent + redémarrage signalé requis** (`FAKE_PENDING_REBOOT=1` en test) : le script
   lance `wsl --install --no-distribution`, détecte le redémarrage requis, enregistre la tâche
   planifiée avec la commande exacte attendue
   (`schtasks /Create /TN EchoHubSetupResume /TR "powershell.exe ... -File \"...\"" /SC ONLOGON /RL HIGHEST /F`),
   avertit l'utilisateur, et se termine proprement en exit 0 (borné : sleep 15 s, pas une
   attente indéfinie) au lieu de rester bloqué.
3. **Docker Desktop absent, `winget` en échec simulé** : le script appelle bien
   `winget install --id Docker.DockerDesktop --exact --silent --accept-package-agreements
   --accept-source-agreements`, puis, sur échec (code non nul), sort avec un message
   actionnable (lien direct docker.com) et exit 1 — pas de crash, pas de trace d'exception brute.
4. **Pilote NVIDIA trop ancien** (`551.23` simulé) : correctement détecté et signalé comme
   insuffisant pour Blackwell (< 570.xx), sans bloquer la suite (avertissement, pas un arrêt).

**Non vérifié — aucune machine Windows disponible** : l'élévation UAC réelle
(`Start-Process -Verb RunAs`), un vrai `wsl --install` avec son vrai redémarrage, une vraie
installation Docker Desktop via `winget`, le déclenchement réel de la tâche planifiée à la
prochaine connexion, et le comportement du pilote NVIDIA/GPU réel. Les scénarios 1 à 4
ci-dessus prouvent le *chemin de contrôle* du script (quelle branche s'exécute, quels
arguments exacts sont passés aux outils externes, quels codes de sortie et quels messages),
pas le comportement des outils Windows eux-mêmes.

## Étape 22 — Complément technique de l'orchestrateur, intégré en cours de mandat

Trois précisions reçues pendant la rédaction, vérifiées contre le code existant :

- **GPU sous WSL2 : `/dev/dxg`, pas `/dev/nvidia*`.** Ni `setup-windows.ps1` ni `start.ps1`
  ne testent un chemin `/dev/nvidia0` côté Linux — les deux s'appuient sur `nvidia-smi.exe`
  (côté Windows) et sur l'exécution réelle d'un conteneur CUDA (`docker run --gpus all ...`),
  ce qui est le bon test. Aucune correction de code nécessaire ; ajouté explicitement au
  README pour que la prochaine équipe ne cherche pas ce chemin par erreur.
- **`libcuda.so` injecté par Windows dans `/usr/lib/wsl/lib`, jamais à écraser** ; si CUDA
  toolkit est installé à la main dans la distribution WSL2, seul `cuda-toolkit-12-x` — jamais
  `cuda`/`cuda-drivers` (pilote Linux embarqué). Ni le script ni ce mandat n'installent quoi
  que ce soit à l'intérieur de la distribution WSL2 (seule `wsl --install -d Ubuntu` crée la
  distro, rien n'y est ensuite installé) — avertissement ajouté au README (section
  Prerequisites) pour l'opérateur qui voudrait le faire lui-même plus tard.
- **CUDA fonctionne aussi nativement depuis WSL2 sur Windows 10 21H2**, pas seulement
  Windows 11 — mentionné au README à titre informatif ; la cible réelle du mandat
  (poste neuf de l'opérateur) reste Windows 11, et `setup-windows.ps1` continue de le
  documenter comme cible testée.
- **`docker-compose.yml` (non modifié, hors périmètre) expose déjà en commentaire
  l'alternative `deploy.resources.reservations.devices`** au cas où la syntaxe CDI
  (`nvidia.com/gpu=all`, validée sur la machine Linux du projet avec un vrai `/dev/nvidia0`)
  ne se résolve pas de la même façon sous le mécanisme WDDM/`dxg` de Docker Desktop. Rendu
  explicite dans le README (section Prerequisites, « GPU passthrough note ») avec la marche à
  suivre exacte si le démarrage échoue précisément sur l'accès GPU.

## Conclusion de ce mandat (installation Windows automatique)

`setup-windows.ps1` produit, marqueur BOM UTF-8 appliqué (comme `start.ps1`/`stop.ps1`),
syntaxiquement valide et compatible PowerShell 5.1 (vérifié par exécution réelle en conteneur
jetable, pas seulement par relecture). README mis à jour : section « Automatic setup » pour
le poste neuf, section Prerequisites enrichie des précisions GPU/WSL2, et section
« What's verified and what isn't » qui distingue explicitement ce qui a été exécuté de ce qui
reste non vérifiable sans machine Windows réelle.
