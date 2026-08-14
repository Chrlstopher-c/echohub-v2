# Rapport de portage Windows — EchoHub

Cible : Windows 10/11, RTX 5090 (32 Go VRAM), architecture Blackwell sm_120.
Source : Arch Linux, RTX 3060 12 Go, architecture Ampere sm_86.

Rédigé au fil de l'eau, zone par zone, pour éviter toute perte de travail.

---

## Partie 1 — Cartographie zone par zone

### 1. Scripts d'orchestration

Constat préalable non listé par les équipes précédentes : EchoHub est une **application Tauri** (Rust +
frontend web), pas un simple couple backend/frontend web. `start.sh` lance `cargo tauri dev` (start.sh:154),
`build.sh` lance `cargo tauri build` (build.sh:8). C'est structurant pour la Partie 2 : Tauri compile
nativement pour Windows (MSVC toolchain), donc la coquille applicative n'est pas le problème — l'orchestration
shell et l'inférence le sont.

**start.sh** (bash, shebang `#!/bin/bash` ligne 1, `set -e` ligne 2) :
- `detect_os()` (start.sh:33-40) ne reconnaît que `arch`, `debian`, `fedora`, `Darwin` (macOS) via `uname` —
  aucune branche Windows, retombe sur `"unknown"` et saute silencieusement `install_deps` sans avertir.
- `install_deps()` (start.sh:45-68) appelle `pacman`/`apt-get`/`dnf`/`brew` — aucun de ces gestionnaires
  n'existe sur Windows (il faudrait `winget`/`choco`, absents du script).
- Installation Rust via `curl | sh` (start.sh:75) — le script d'installation Unix de rustup, incompatible ;
  Windows utilise `rustup-init.exe`.
- Installation Bun via `curl -fsSL https://bun.sh/install | bash` (start.sh:84) — nécessite bash ; Bun fournit
  un script PowerShell dédié (`irm bun.sh/install.ps1 | iex`) que le script n'utilise pas.
- `python3 -m venv .venv` (start.sh:94) puis **`.venv/bin/pip`** codé en dur (start.sh:98-99) — sur Windows le
  venv place l'exécutable dans `.venv\Scripts\pip.exe`, pas `.venv/bin/`. Cassera tel quel.
- `$HOME/.local/share/echohub/vllm-envs` (start.sh:18, start.sh:105) — `$HOME` et le chemin XDG n'existent pas
  nativement sous Windows (il faudrait `%LOCALAPPDATA%` ou équivalent).
- `find ... -exec rm -rf` et `find ... -delete` pour vider le cache Python (start.sh:143-144) — commandes Unix
  sans équivalent natif Windows.
- `> "$ROOT/logs/backend.log"` (start.sh:149-150) — la redirection de troncature fonctionne en PowerShell avec
  une syntaxe différente ; en `cmd.exe` `>` tronque aussi mais le script entier n'est pas portable tel quel.
- Détection Wayland/X11 (start.sh:122-130) : sans effet sur Windows, à ignorer proprement plutôt qu'à porter.
- `exec cargo tauri dev` (start.sh:154) : `exec` est une construction bash ; sous Windows la commande finale
  serait simplement `cargo tauri dev`, sans `exec`.

**stop.sh** et **restart.sh** :
- Pidfiles écrits sous `/tmp/echohub_*.pid` (stop.sh:4, restart.sh:10) — `/tmp` n'existe pas nativement sous
  Windows (seulement sous WSL/Git Bash/Cygwin).
- `kill -0 "$pid"` et `kill "$pid"` (stop.sh:7, restart.sh:13) — signaux POSIX, sans équivalent direct ;
  Windows utilise `taskkill /PID <pid> /F`.
- `pkill -f "vllm.entrypoints"`, `pkill -f "uvicorn.*echohub"`, `pkill -f "target/debug/app"` (stop.sh:12-14),
  et `pkill -f "uvicorn backend.main"`, `pkill -f "cargo-tauri tauri dev"`, `pkill -f "vite.*echohub"`,
  `pkill -f "vllm.entrypoints"` (restart.sh:19-22) — `pkill` absent de Windows ; il faudrait `Get-Process` +
  filtrage par ligne de commande via PowerShell/WMI.
- `restart.sh:28` : `exec "$ROOT/start.sh"` — même remarque `exec`.

**build.sh** : shebang bash (ligne 1), sinon ne contient que `bun run build` et `cargo tauri build`, qui sont
en eux-mêmes portables. Le script conteneur doit être réécrit (PowerShell `.ps1` ou batch), pas son contenu.

**Verdict de zone** : aucun de ces quatre scripts ne s'exécute tel quel sous `cmd.exe`/PowerShell natif. Ils
tournent sans modification sous Git Bash ou WSL2 (bash présent), à l'exception des chemins `.venv/bin/` et
`/tmp` qui resteraient à corriger même sous Git Bash puisque Python et le PID management restent Windows-natifs
en dessous. Portage mécanique : réécriture complète en PowerShell recommandée pour un Windows natif propre ;
sinon, Git Bash comme couche de compatibilité minimale + correctifs ciblés (chemins venv, pidfiles).

### 2. Backend Python

**Chemins `bin/python` codés en dur — recensement exhaustif (confirmé, 20 occurrences) :**
- `backend/services/engine_router.py:132` — `legacy / "bin" / "python"`
- `backend/services/vllm_service.py:36` et `:43` — `.venv-vllm/bin/python` (`VLLM_PYTHON`)
- `backend/services/llama_server_config.py:28` — `DEFAULT_BIN` sous `~/.unsloth/llama.cpp/build-cuda/bin/llama-server`
- `backend/services/finetune_service.py:26` — `_UNSLOTH_VENV / "bin" / "python"`
- `backend/services/finetune_service.py:393` — `build/bin/llama-quantize`
- `backend/services/finetune_service.py:580` — `~/.unsloth/llama.cpp/build/bin/llama-cli`
- `backend/services/mcp_manager.py:555` — `skill_dir / ".venv" / "bin" / "python"`
- `backend/routers/installer.py:73, 108, 130, 248, 264, 442` — `.venv/bin/python` et `.venv/bin/pip` à
  6 endroits distincts du flux d'installation
- `backend/services/vllm_manager.py:52, 173, 187, 210, 230, 280, 336, 337` — 8 occurrences, gestion des
  environnements vLLM versionnés
Tous cassent tel quel sous Windows : le layout `venv` y place les exécutables dans `Scripts\` et ajoute `.exe`
(`Scripts\python.exe`, `Scripts\pip.exe`). Correctif mécanique unique et systématique possible : une fonction
utilitaire centrale `venv_python(venv_dir)` / `venv_pip(venv_dir)` qui bifurque sur `os.name == "nt"`, à
substituer aux ~20 constructions actuelles.

**`start_new_session=True` (confirmé)** :
- `backend/services/vllm_service.py:290` — `subprocess.Popen(cmd, ..., start_new_session=True, env=env)`
- `backend/services/llama_server_service.py:156` — même paramètre.
`start_new_session` appelle `setsid()` en interne, absent sur Windows ; `subprocess.Popen` lève une
`ValueError: start_new_session is not supported on Windows platforms`. Remplacement Windows :
`creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` (voire `DETACHED_PROCESS`), branché sur `os.name`.

**Signaux POSIX — au-delà de ce que les équipes précédentes avaient noté**, `signal.SIGKILL` n'existe
tout simplement pas dans le module `signal` sous Windows (`AttributeError`, pas juste "non supporté") :
- `backend/services/vllm_process.py:37,41,46` — `os.kill(pid, signal.SIGTERM)` puis boucle de polling
  `os.kill(pid, 0)` puis `os.kill(pid, signal.SIGKILL)` (ligne 46) : cette dernière ligne plante au chargement
  de l'attribut sur Windows, avant même l'appel.
- `backend/services/llama_server_service.py:66,70,74` — même triptyque SIGTERM/poll/SIGKILL.
- `backend/services/mcp_manager.py:606,609` — idem pour les processus MCP stdio.
- `backend/routers/connectors.py:244,249` — sidecar Discord : `send_signal(signal.SIGTERM)` puis SIGKILL
  implicite (log ligne 249), même faille.
`os.kill(pid, 0)` pour tester la vivacité d'un process (pattern POSIX de "kill signal 0") ne fonctionne pas
non plus de façon fiable sous Windows. Solution portable : `psutil` (déjà une dépendance du projet, voir
requirements ligne `psutil>=5.9.0`) expose `Process.terminate()` / `Process.kill()` / `Process.is_running()`
de façon cross-platform et doit remplacer ces 4 foyers de `os.kill`/`signal.SIG*`.

**Pidfile en chemin POSIX en dur (nouveau, non signalé par les équipes précédentes)** :
`backend/services/vllm_process.py:14` — `VLLM_PID_FILE = Path("/tmp/echohub_vllm.pid")`. `/tmp` n'existe pas
nativement sous Windows ; ce module écrit un fichier de PID totalement hors service dès le premier lancement
Windows. Doit passer par `tempfile.gettempdir()`.

**`os.access(path, os.X_OK)`** — `backend/services/llama_server_config.py:105`, utilisé pour vérifier que le
binaire `llama-server` est exécutable avant de le lancer. Windows n'a pas de bit d'exécution POSIX ; l'appel
ne lève pas, mais son résultat n'est pas significatif (il faut se rabattre sur l'extension `.exe` ou une
tentative d'exécution).

**Branches de plateforme existantes** :
- `backend/services/finetune_service.py:24` — seul fichier à tester `sys.platform == "win32"` ; gère déjà la
  variante CUDA `cu130`. Confirmé, aucune autre trouvaille à ajouter ici.
- `backend/routers/installer.py:61` — `platform.system() == "Darwin"` pour la branche Metal, aucune branche
  Windows équivalente. `installer.py:229` log `platform.system()` mais ne branche que sur Darwin ailleurs
  (lignes 153-167 et 360-391 : Linux/CUDA implicite, ROCm, Metal — pas de cas Windows/CUDA distinct alors que
  la chaîne de compilation CMake diffère : MSVC + `nvcc` au lieu de gcc).
- `installer.py:449` et `vllm_manager.py:353` : `vllm==0.21.0` figé en dur, confirmé.

**Dépendances sans roue Windows** : aucune trouvée dans `backend/requirements.txt` (fastapi, uvicorn[standard],
huggingface_hub, loguru, pydantic, httpx, python-dotenv, gitpython, pyyaml, llama-cpp-python, psutil,
chromadb>=1.5.0) — toutes ont des roues Windows officielles ou se compilent avec MSVC. Pas de `uvloop`,
`fcntl`, `os.fork`, `pwd`, `grp` détectés dans `backend/services` ni `backend/routers` (grep exhaustif, confirmé
négatif) — la seule dépendance réellement bloquante reste `llama-cpp-python` compilé depuis les sources (CMake
+ nvcc), traité en zone 6.

**Verdict de zone** : le backend est majoritairement portable ; le vrai travail est mécanique (chemins venv,
signaux, pidfile) sauf sur un point d'architecture — `installer.py` doit gagner une branche Windows complète
(toolchain MSVC + CUDA) symétrique à ses branches Darwin/Linux existantes.

### 3. Serveur MCP et connecteurs

**`mcp_server.py` (racine, 325 lignes)** — serveur MCP exposé à Claude Code via `FastMCP`, transport
**stdio uniquement** (`mcp.run(transport="stdio")`, ligne 324). Il ne fait que proxier en HTTP/JSON vers
l'API interne d'EchoHub sur `127.0.0.1:37821` (ligne 27) via `httpx.AsyncClient`. Aucune primitive
POSIX : pas de socket brut, pas d'usage de `os`, pas de chemin en dur. **Portable tel quel sur Windows** —
seul son mode d'enregistrement change : la commande `claude mcp add -s user echohub -- <python> <ce_fichier>`
(ligne 8) doit pointer vers `<venv>\Scripts\python.exe` au lieu de `<venv>/bin/python`, cohérent avec le
constat de la zone 2.

**Connecteurs MCP (`backend/services/mcp_manager.py`, 676 lignes)** :
- Transport HTTP local pour les serveurs MCP "process" : `socket.socket(socket.AF_INET, socket.SOCK_STREAM)`
  (mcp_manager.py:345) pour sonder la disponibilité d'un port dans la plage 38000-38099 (message d'erreur
  ligne 349) — `AF_INET`/`SOCK_STREAM` sont cross-platform, aucun souci.
- `_STDIO_LAUNCHERS = ("uvx", "npx", "node", "python", "python3")` (mcp_manager.py:86) : **point d'attention
  non levé par les équipes précédentes.** Sous Windows, `npx` et `node` installés via l'installeur officiel
  sont des scripts `.cmd`/`.bat`, pas des exécutables natifs. `asyncio.create_subprocess_exec` (utilisé dans
  `mcp_stdio_client.py:89`) appelle directement `CreateProcess` sans passer par un interpréteur de commandes ;
  lancer `"npx"` sans l'extension exacte échoue typiquement avec `FileNotFoundError` sur Windows (piège
  documenté côté écosystème MCP/Claude Desktop). Il faudra résoudre l'exécutable via `shutil.which()` (qui
  gère `PATHEXT` correctement) avant l'appel, ou lancer via `shell=True` pour ces launchers spécifiquement.
- Manipulation globale de `os.environ` pour les connecteurs (mcp_manager.py:569-575 : `os.environ.copy()` /
  `.update()` / `.clear()` / restauration) : mécanisme cross-platform mais non thread-safe si l'event loop
  interagit avec d'autres coroutines pendant la fenêtre — pas spécifique à Windows, signalé pour mémoire.
- Encodage : `mcp_stdio_client.py:194,201,222` — `.encode()` sans charset explicite (UTF-8 par défaut en
  Python 3, indépendant de la plateforme, donc sûr) ; `mcp_stdio_client.py:249` — `raw.decode(errors="replace")`
  également sûr. `connectors.py:81` — `raw.decode("utf-8", errors="replace")`, explicite et sûr.

**Sidecar Discord (`backend/routers/connectors.py`)** : lancé via `subprocess` avec `env={**os.environ, ...}`
(ligne 199) puis `Popen(..., env=env)` (ligne 209) — rien de spécifique Unix dans le lancement lui-même ; seul
le SIGTERM/SIGKILL de l'arrêt (déjà couvert en zone 2, lignes 244-249) est à corriger.

**Event loop asyncio** : `uvicorn[standard]` (requirements.txt) installe `uvloop` comme extra, mais `uvloop`
porte un marqueur d'environnement `sys_platform != 'win32'` dans son propre `pyproject` — `pip install` saute
automatiquement cette dépendance sous Windows et uvicorn retombe sur la boucle asyncio standard
(`ProactorEventLoop`, qui supporte `create_subprocess_exec`). Aucune action requise ici ; à vérifier une fois
seulement en installant réellement sous Windows (non fait dans cette revue statique).

**Verdict de zone** : `mcp_server.py` lui-même ne demande aucun changement. Le seul risque réel est la
résolution des launchers `npx`/`node` par `mcp_manager.py`, un piège Windows classique et non trivial à
repérer sans test réel — à traiter en priorité basse (uniquement si des connecteurs MCP tiers en JavaScript
sont utilisés) mais à corriger avant de promettre le support des connecteurs communautaires npm sous Windows.

### 4. Frontend

**Runtime attendu** : Bun (`frontend/package.json` scripts `dev`/`build`/`preview` via `vite`), React 18,
TypeScript, Tailwind. Dépendances npm listées (`@tauri-apps/api`, `framer-motion`, `highlight.js`, `react`,
`react-markdown`, etc.) — aucune n'a de partie binaire native compilée (pas de `node-gyp`), toutes portables
Windows sans changement.

**Trouvaille majeure, non signalée par les équipes précédentes : le code Rust natif de l'application Tauri
(`frontend/src-tauri/src/lib.rs`) contient lui-même du code Unix-only compilé dans le binaire final — ce
n'est pas un problème de script, mais un problème de code source Rust à corriger et recompiler.**

- `find_python()` (lib.rs:121-144) construit des chemins avec un séparateur `/` en dur :
  `format!("{}/backend/.venv/bin/python", root)` (ligne 124) et `.../bin/python3` (ligne 125). Le test de
  chemin absolu `candidate.starts_with('/')` (ligne 130) suppose une racine POSIX (`/...`) ; sous Windows, une
  racine typique commence par une lettre de lecteur (`C:\...`), donc cette branche n'est jamais empruntée et
  la fonction retombe systématiquement sur la recherche via `which` (ligne 136) — binaire **absent de
  Windows** (l'équivalent est `where`). Résultat : sur Windows, `find_python()` ne trouve jamais le venv du
  projet et retombe sur le `"python3"` générique du `PATH` (ligne 143), pas le venv du backend.
- `spawn_backend_with_retries()` (lib.rs:147-165) appelle `std::process::Command::new("find")` avec la
  syntaxe GNU `find <dir> -type d -name __pycache__ -exec rm -rf {} +` (lignes 158-164) pour vider le cache
  Python bytecode à chaque redémarrage — `find` et `rm` sont absents de Windows nativement ; l'appel échoue
  silencieusement (le résultat est jeté via `.output()` sans vérification, ligne 164), donc sans crash mais
  sans effet : le cache bytecode ne serait jamais nettoyé sous Windows.
- `read_clipboard_image_wayland()` (lib.rs:39-74) invoque le binaire `wl-paste` (lignes 43, 53) — spécifique
  à Wayland/Linux. Correctement contourné par un test `WAYLAND_DISPLAY` (ligne 32) qui bascule vers
  `read_clipboard_image_arboard()` (ligne 76) sur les autres plateformes ; `arboard` (Cargo.toml, dépendance
  déjà présente) supporte nativement le presse-papiers Windows — **cette fonction est déjà portable en
  l'état**, aucune action requise au-delà de la vérification du comportement réel sous Windows.
- `find_free_port()` (lib.rs:11-19) et `kill_backend()` (lib.rs:223-233, via `CommandChild::kill()` du
  plugin `tauri-plugin-shell`) sont écrits avec les abstractions `std::net` et le plugin Tauri — portables
  sans changement.
- `locate_project_root()` (lib.rs:240-248) déduit la racine du projet par profondeur fixe d'ancêtres du
  chemin de l'exécutable (`nth(5)`) — structure de build identique sous Windows (`target/{profile}/app.exe`),
  ne devrait pas casser mais reste non vérifié en pratique.

**Configuration Tauri (`tauri.conf.json`)** :
- `"beforeDevCommand": "VITE_MSW=false bun run dev"` (ligne 9) — syntaxe `VAR=valeur commande` est une
  construction shell POSIX (bash/zsh) ; `cmd.exe` et PowerShell natifs ne l'interprètent pas ainsi (PowerShell
  utilise `$env:VITE_MSW="false"; bun run dev`, `cmd.exe` utilise `set VITE_MSW=false && bun run dev`). À
  remplacer par `cross-env VITE_MSW=false bun run dev` (paquet npm cross-platform) pour rester unique entre
  OS, ou par une commande conditionnelle.
- `"bundle.targets": ["appimage", "deb"]` (lignes 30-33) — uniquement des cibles Linux ; il manque `"msi"`
  et/ou `"nsis"` pour produire un installeur Windows. Bonne nouvelle : `icons/icon.ico` est déjà présent
  dans le tableau d'icônes (bundle.icon), donc l'actif graphique Windows existe déjà, seule la section
  `"windows"` de bundle (WiX/NSIS) reste à ajouter.
- CSP (ligne 25) autorise `connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*` — cohérent avec l'usage de
  loopback uniquement (backend Python sur `127.0.0.1`), aucune dépendance à un nom d'hôte POSIX.

**Verdict de zone** : le frontend web (Bun/Vite/React) est portable sans changement. Le point structurant est
le code Rust de la coquille Tauri : `find_python()` et le nettoyage de cache via `find`/`rm` doivent être
réécrits avec des primitives Rust cross-platform (`std::env::consts::EXE_SUFFIX`, test de préfixe de racine
via `Path::is_absolute()` au lieu de `starts_with('/')`, et `std::fs::remove_dir_all` avec un parcours natif
`walkdir` au lieu du binaire `find`). C'est un correctif mécanique, mais en Rust compilé — donc il exige une
recompilation complète de la coquille Tauri pour Windows, pas un simple ajustement de script.

### 5. Couche données (ChromaDB, SQLite)

**Correction utile aux trouvailles précédentes** : `backend/services/user_data.py:8-29`
(`get_user_data_dir()`) **gère déjà nativement Windows**, contrairement à l'affirmation de départ selon
laquelle « aucun autre fichier clé n'a de branche Windows » — celle-ci reste vraie pour `installer.py`, mais
`user_data.py` en est une exception réelle et fonctionnelle : `platform.system() == "Windows"` (ligne 18)
résout `%APPDATA%\echohub` (lignes 19-20), avec repli macOS (`~/Library/Application Support`, ligne 22) et
Linux/XDG (ligne 24). C'est le chemin canonique de stockage utilisateur pour tout le projet — toutes les
bases qui en dépendent héritent donc du bon comportement Windows sans modification.

- `get_db_path()` (user_data.py:32-33) → `<user_data_dir>/echohub.db` — sur Windows :
  `%APPDATA%\echohub\echohub.db`.
- `get_logs_dir()` (user_data.py:36-39) → `<user_data_dir>/logs`.
- `get_config_path()` (user_data.py:42-43) → `<user_data_dir>/config.json`.

**SQLite (`backend/services/db.py`)** :
- `sqlite3.connect(str(db_path), check_same_thread=False)` (db.py:20) avec `PRAGMA journal_mode=WAL` (ligne
  21) — le mode WAL de SQLite est documenté comme non fiable sur systèmes de fichiers réseau (NFS/SMB), mais
  fonctionne normalement sur un disque local NTFS ; **aucun problème attendu** pour un déploiement Windows
  standard (poste local, pas de partage réseau). Point de vigilance uniquement si l'utilisateur final stocke
  `%APPDATA%` sur un lecteur réseau synchronisé (OneDrive géré en entreprise, lecteur mappé) — cas hors
  périmètre de ce rapport, à documenter comme limitation connue plutôt qu'à corriger.
- Connexion par thread via `threading.local()` (db.py:14, 18) — portable, ne dépend d'aucune primitive POSIX.
- `PRAGMA foreign_keys=ON` (db.py:22) — comportement SQLite standard, indépendant de l'OS.

**ChromaDB (`backend/services/memory_service.py`)** :
- `_CHROMA_DIR` (ligne 18) résout soit la variable d'environnement `CHROMA_DIR`, soit
  `get_user_data_dir() / "chromadb"` — hérite donc du même chemin Windows-safe que SQLite.
  `chromadb.PersistentClient(path=str(_CHROMA_DIR), ...)` (lignes 26-29) : ChromaDB publie des roues
  Windows officielles (dépendance `chromadb>=1.5.0` dans requirements.txt, confirmée en zone 2), aucune
  compilation requise à l'installation standard.
- **Constat annexe hors mandat de correction (signalé, non traité)** : un fichier `chroma.sqlite3` existe à
  la racine du dépôt (`/mnt/projects/echohub/chroma.sqlite3`), en dehors de `get_user_data_dir()`. C'est
  vraisemblablement une base de développement créée avant la migration vers le répertoire utilisateur
  standard, ou un artefact laissé par un run avec `CHROMA_DIR` non défini pointant sur le CWD. Sans incidence
  sur le portage (le code de production n'y écrit pas), mais à ne pas confondre avec les données réelles
  situées sous `~/.local/share/echohub/chromadb` en usage normal Linux.
- Verrouillage de fichiers : ChromaDB en mode `PersistentClient` embarque son propre moteur (SQLite +
  index HNSW binaire) avec le même modèle de verrouillage que SQLite classique — pas de dépendance
  supplémentaire à un verrou POSIX (`fcntl`) détectée dans le code du projet lui-même (le verrouillage se
  fait à l'intérieur du paquet `chromadb`, hors périmètre du code EchoHub).

**Verdict de zone** : c'est la zone la plus favorable du rapport. La couche données est déjà portable —
`get_user_data_dir()` fait le travail de résolution de chemin correctement pour Windows, SQLite et ChromaDB
n'ont pas de dépendance Unix-only. Aucune action de portage requise ici au-delà d'un test réel de
`%APPDATA%\echohub` en conditions Windows (non exécuté dans cette revue statique).

### 6. Inférence locale (les trois moteurs)

**Moteur 1 — llama-cpp-python (in-process)** :
- `backend/services/llama_service.py` : backend principal GGUF, `n_gpu_layers=-1` (offload complet),
  `flash_attn=True` par défaut (`_flash_attn_enabled()`, ligne 60-65, lit `config_service`).
- Compilé depuis les sources par l'installeur (`backend/routers/installer.py:346-395`, fonction
  `_compile_llama_async`) — confirmé : `CMAKE_ARGS="-DGGML_CUDA=on"` (ligne 367 branche générique), avec une
  branche spécifique **Arch Linux** (`Path("/etc/arch-release").exists()`, ligne 354) qui ajoute
  `NVCC_CCBIN=/usr/bin/gcc-15` et `CUDA_PATH=/opt/cuda` (lignes 357-364) — entièrement Unix, aucun équivalent
  Windows. Sous Windows, la chaîne de compilation change de nature : MSVC (`cl.exe`) + `nvcc`, avec
  `CUDA_PATH` positionné automatiquement par l'installeur NVIDIA (bonne nouvelle relative), mais aucune
  branche `platform.system() == "Windows"` n'existe dans `_compile_llama_async` — à écrire entièrement.
  La branche ROCm (lignes 369-386, chemins `/opt/rocm` etc.) est hors périmètre RTX 5090.
- Roue précompilée Windows CUDA disponible dans l'écosystème (ex. communauté HuggingFace
  `llama-cpp-python-windows-blackwell-cuda`) mais rien d'officiel packagé pour sm_120 — la compilation depuis
  les sources reste la voie fiable, confirmant que l'installeur doit gagner du CMake configuré MSVC.

**Moteur 2 — binaire llama.cpp compilé CUDA (llama-server, port 37824)** :
- `backend/services/llama_server_config.py:24-28` — `LLAMA_SERVER_PORT = 37824` confirmé, `DEFAULT_BIN`
  sous `Path.home() / ".unsloth" / "llama.cpp" / "build-cuda" / "bin" / "llama-server"` (ligne 28) —
  `Path.home()` résout correctement le profil utilisateur sous Windows, mais le nom de fichier littéral
  `"llama-server"` sans suffixe manque l'extension `.exe` attendue par Windows ; `resolve_binary()`
  (ligne 55+) doit ajouter `.exe` conditionnellement (`os.name == "nt"`).
- `os.access(path, os.X_OK)` (ligne 105, déjà signalé en zone 2) rend le contrôle d'exécutabilité non
  significatif sous Windows.
- La documentation intégrée au fichier (lignes 6-9) qualifie déjà cet emplacement de « fragile », avec
  possibilité de surcharge via `ECHOHUB_LLAMA_SERVER_BIN` — bon point d'ancrage pour le portage : il suffit de
  documenter/pré-remplir cette variable d'environnement avec un chemin Windows lors de l'installation, sans
  changer la logique de résolution.
- `start_new_session=True` confirmé (`llama_server_service.py:156`, déjà couvert zone 2).

**Moteur 3 — vLLM 0.21.0 (modèles AWQ)** :
- Version figée confirmée : `installer.py:449` et `vllm_manager.py:353` (`vllm==0.21.0`).
- `vllm_service.py:288` — l'environnement de lancement inclut déjà
  `VLLM_WORKER_MULTIPROC_METHOD: "spawn"` — bonne nouvelle non signalée par les équipes précédentes : c'est
  précisément la méthode de multiprocessing sûre et déjà celle utilisée par défaut sous Windows (où `fork`
  n'existe pas) ; aucun changement requis sur ce point.
- `start_new_session=True` confirmé (`vllm_service.py:290`, déjà couvert zone 2).
- Support AWQ sur vLLM en général : des rapports communautaires (issue vLLM #37242, forum vLLM AWQ report)
  décrivent AWQ fonctionnel sur SM_120 via le kernel `awq_marlin`, avec des débits mesurés autour de
  140 tok/s sur un Qwen3-14B-AWQ sur RTX 5090 — mais aucune confirmation trouvée spécifique à la version
  épinglée **0.21.0** ; la plupart des rapports positifs concernent des builds nightly ou des versions plus
  récentes que celles figées ici. **Point non tranché à ce niveau, traité avec sources en Partie 2.**

**Aucun modèle par défaut en dur côté chargement backend** : confirmé — le choix du modèle vient de
l'interface (`ModelInfo` passé à `load()`), mais **nuance à noter** : `mcp_server.py:31` définit
`DEFAULT_MODEL_ID = "Jackrong/Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF"` comme modèle par
défaut du serveur MCP côté Claude Code (pas du backend principal) — ce n'est pas contradictoire avec la
trouvaille de départ (qui concerne le chargement dans l'UI), mais mérite d'être signalé car ce modèle précis
apparaît directement concerné par la limitation flash-attn ci-dessous.

**Piste flash-attn / head_dim > 128 sur sm_120 — tranchée, avec source** :
Confirmé par la documentation communautaire de flash-attn pour Blackwell (dépôt `flash-attention_sm120`,
analyses `fa_utils.py` de vLLM) : **SM120 ne supporte pas head_dim > 128 pour Flash Attention v4/native**
— le budget de mémoire partagée (SMEM, 99 Ko) ne peut pas contenir la tuile Q pour ces dimensions. Les
architectures citées comme directement affectées sont explicitement **Qwen3.5-9B (head_dim=256)** et
Qwen3-Coder-Next (head_dim=256) — le premier étant exactement le modèle par défaut du serveur MCP d'EchoHub
(`mcp_server.py:31`). vLLM contourne déjà ce cas via `fa_utils.py`, qui route les `head_size > 128` vers
Flash Attention v2 (repli fonctionnel mais plus lent) sur Blackwell plutôt que de planter. Conclusion : la
pile **fonctionne** avec ce modèle sur sm_120, mais **sans l'accélération Flash Attention v4 native** — un
repli automatique existe côté vLLM, mais llama.cpp/llama-cpp-python n'ont pas la même logique de repli
documentée et devront être testés spécifiquement avec ce modèle sur le matériel cible.
Sources : [flash-attention_sm120 (GitHub)](https://github.com/roy86/flash-attention_sm120),
[Flash Attention on sm_121 — Medium](https://medium.com/@rakshith.d26/flash-attention-on-sm-121-solving-pytorch-compatibility-on-blackwell-gb10-a83d9ff3cf9b).

**Verdict de zone — la plus structurante du rapport** : les trois moteurs sont individuellement portables en
architecture (aucune primitive Unix bloquante dans leur logique métier au-delà de ce qui est déjà couvert en
zone 2), mais leur **chaîne de compilation/installation** est le vrai obstacle : `installer.py` doit gagner
une branche Windows complète pour `llama-cpp-python` (MSVC + nvcc + CUDA_PATH), et le support réel de
Blackwell sm_120 par la version exacte de vLLM épinglée (0.21.0) reste à valider empiriquement — la
littérature confirme le support sm_120 en général mais pas sur cette version précise. Détail chiffré et
sourcé en Partie 2.

### 7. Documentation

**Mention Windows confirmée, unique et isolée** : `README.md:49`, dans la liste des prérequis :
« A GPU (NVIDIA recommended, AMD and Apple Silicon work too) / 8 GB+ of GPU memory / 20–50 GB of disk space
/ **Linux, macOS, or Windows (WSL2)** ». C'est la seule occurrence de « Windows » ou « WSL » dans toute la
documentation du dépôt (`README.md`, `docs/*.md`, `STATE.md`, `TODO.md`, `ARBORESCENCE.md` — grep exhaustif,
confirmé négatif partout ailleurs).

**Ce que cette ligne ne tient pas** : `start.sh:33-40` (`detect_os()`, zone 1) ne reconnaît que `arch`,
`debian`, `fedora` et `Darwin` — aucune branche WSL2/Windows, donc `install_deps()` ne s'exécuterait même pas
sous une distribution WSL2 non listée (Ubuntu WSL2 tomberait dans la branche `debian` par coïncidence de
`/etc/debian_version`, ce qui *pourrait* fonctionner partiellement en WSL2 Ubuntu, mais c'est un hasard de
détection, pas un support voulu ni testé). Pour Windows natif (hors WSL2), aucune des quatre commandes
(`start.sh`, `stop.sh`, `restart.sh`, `build.sh`) ne s'exécute sans un shell bash tiers (Git Bash/WSL).

**Promesse la plus optimiste, à corriger en priorité si Windows natif est visé** : `README.md:51` —
« You don't need Python knowledge or configuration files. No terminal access after the first install. » Cette
promesse suppose un installeur graphique de bout en bout (`InstallerApp`, `backend/routers/installer.py`)
capable de compiler `llama-cpp-python` et d'installer vLLM sans intervention utilisateur. Sur Linux, cet
installeur a déjà une logique par distribution (zone 6) ; sur Windows, il faudrait soit embarquer un
toolchain MSVC + CUDA complet (lourd, fragile), soit revoir la promesse « aucun terminal » pour une cible
Windows — l'écart entre la promesse et l'état réel du code est le plus large de tout le rapport.

**`docs/llama-server.md`** : documentation technique correcte et cohérente avec le code (confirme l'ordre de
résolution du binaire : `ECHOHUB_LLAMA_SERVER_BIN` > `config.json` > défaut `~/.unsloth/...` > `PATH`,
lignes 19-23) — ne mentionne aucune spécificité Windows, mais ne contredit rien non plus ; à compléter d'une
section Windows (nom de binaire `.exe`, chemin `%USERPROFILE%\.unsloth\...`) plutôt qu'à corriger.

**Verdict de zone** : la documentation ne ment pas gravement, mais elle affirme un support (« Windows (WSL2) »)
qu'aucun script ni aucune branche de code ne concrétise, et elle promet une installation sans terminal qui
n'est vraie sur aucune plateforme actuelle de façon garantie, encore moins sur Windows. À corriger dans le
même mouvement que le portage effectif — documenter WSL2 seulement une fois réellement testé, ou retirer la
mention jusque-là.

---

## Partie 2 — Comparaison des voies : natif Windows / WSL2 / Docker complet

### Les deux questions tranchées

**1. Le support réel de Blackwell sm_120 par la pile actuelle (PyTorch, vLLM 0.21.0, noyaux AWQ, flash-attn,
llama.cpp compilé) — tranché : support réel mais partiel, et sensible à la version exacte.**

- **PyTorch** : support officiel sm_120 depuis la version 2.7.0, avec roues CUDA 12.8 pré-construites
  (cuDNN, NCCL, Triton 3.3 mis à jour). Toute image ou installation `-cuda12.8-` en 2.7.0+ fonctionne sur
  RTX 50-series. Source :
  [PyTorch issue #159207](https://github.com/pytorch/pytorch/issues/159207),
  [discussion PyTorch Forums](https://discuss.pytorch.org/t/is-there-a-pytorch-build-that-supports-nvidia-rtx-5090-compute-capability-12-0-sm-120/223536).
- **vLLM / AWQ** : le kernel `awq_marlin` fonctionne sur SM_120 d'après des rapports de terrain (RTX 5060 Ti,
  RTX 5090), avec des débits mesurés autour de 140 tok/s sur Qwen3-14B-AWQ. **Mais** aucune source trouvée ne
  confirme spécifiquement ce comportement sur la version **exacte 0.21.0** épinglée par EchoHub — les rapports
  positifs concernent majoritairement des builds nightly ou des versions plus récentes. Source :
  [vLLM forum — AWQ field report SM_120](https://discuss.vllm.ai/t/field-report-awq-on-rtx-5060-ti-sm-120-blackwell-awq-marlin-triton-attn-working/2463),
  [vLLM issue #37242](https://github.com/vllm-project/vllm/issues/37242).
- **flash-attn** : limitation confirmée et documentée — SM120 ne supporte pas `head_dim > 128` en Flash
  Attention v4 native (budget SMEM 99 Ko insuffisant pour la tuile Q). vLLM contourne via repli automatique
  vers FA2 (`fa_utils.py`) quand `head_size > 128` sur Blackwell. Modèles directement concernés cités dans
  les sources : Qwen3.5-9B et Qwen3-Coder-Next (head_dim=256) — dont le premier est précisément le modèle par
  défaut du serveur MCP d'EchoHub. Source :
  [flash-attention_sm120 (GitHub)](https://github.com/roy86/flash-attention_sm120),
  [Flash Attention on sm_121 — Medium](https://medium.com/@rakshith.d26/flash-attention-on-sm-121-solving-pytorch-compatibility-on-blackwell-gb10-a83d9ff3cf9b).
- **llama.cpp compilé CUDA** : CUDA Toolkit 12.8 est la première version à connaître les cibles Blackwell
  (sm_100/sm_101/sm_120) ; une toolkit antérieure fait échouer `nvcc`. Des échecs de compilation restent
  documentés sur des cas spécifiques (kernels MXFP4 en PTX, segfault MMQ avec CUDA 13.1) — le contournement
  rapporté est de forcer cuBLAS plutôt que les kernels CUDA maison de ggml. Source :
  [llama.cpp issue #19662](https://github.com/ggml-org/llama.cpp/issues/19662),
  [runaihome.com — llama.cpp build fixes 2026](https://runaihome.com/blog/llama-cpp-build-cuda-errors-fix-2026/).
- **Conclusion tranchée** : la pile fonctionne sur sm_120 avec CUDA 12.8+, mais (a) `vllm==0.21.0` figé doit
  être revérifié empiriquement plutôt que supposé compatible par extrapolation des versions plus récentes,
  et (b) llama.cpp doit être recompilé avec CUDA Toolkit 12.8+ et potentiellement forcer cuBLAS si les
  kernels maison échouent. Aucun élément ne bloque définitivement le portage ; tout est affaire de version
  exacte des toolchains, pas d'incompatibilité d'architecture.

**2. Le passthrough GPU sous Docker Desktop Windows via WSL2 et le NVIDIA Container Toolkit — tranché :
fonctionnel, à conditions précises.**

- Architecture : WSL2 exécute un noyau Linux réel dans une VM Hyper-V légère avec passthrough matériel par
  GPU-PV (GPU Paravirtualization). **Le pilote NVIDIA Linux ne doit jamais être installé à l'intérieur de
  WSL2** — seul le CUDA Toolkit doit l'être ; le pilote vient de Windows et expose `libcuda.so` en stub côté
  Linux. Installer le pilote Linux dans WSL2 casse la chaîne de passthrough. Source :
  [NVIDIA CUDA on WSL User Guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html),
  [Microsoft Learn — Enable NVIDIA CUDA on WSL2](https://learn.microsoft.com/en-us/windows/ai/directml/gpu-cuda-in-wsl).
- Le NVIDIA Container Toolkit s'installe ensuite normalement à l'intérieur de la distribution WSL2 (comme sur
  un Linux natif), et Docker Desktop l'exploite via son intégration WSL2. Source :
  [Docker blog — WSL2 GPU support](https://www.docker.com/blog/wsl-2-gpu-support-for-docker-desktop-on-nvidia-gpus/).
- Image de base CUDA : pour compiler `llama-cpp-python` avec `nvcc` (confirmé zone 6, `installer.py` utilise
  `CMAKE_ARGS="-DGGML_CUDA=on"`), l'image doit être une variante **`devel`**, pas `runtime` — confirmé par les
  trouvailles de départ et par la pratique communautaire : `nvidia/cuda:12.8.0-devel-ubuntu22.04` (ou plus
  récent) est la base recommandée pour Blackwell, car `devel` inclut les en-têtes et `nvcc` que `runtime`
  n'a pas. Source : [nvidia/cuda sur Docker Hub](https://hub.docker.com/r/nvidia/cuda),
  [SaladCloud — PyTorch RTX 5090](https://docs.salad.com/container-engine/tutorials/machine-learning/pytorch-rtx5090).
- **Conclusion tranchée** : le passthrough GPU fonctionne sous Docker Desktop Windows + WSL2, à trois
  conditions cumulatives : pilote NVIDIA Windows à jour (branche Blackwell/CUDA 12.8+), *aucun* pilote Linux
  installé dans la distro WSL2, et image de base `nvidia/cuda:12.8.x-devel-<distro>` pour toute étape de
  compilation (`llama-cpp-python`). Une image `runtime` suffirait seulement pour exécuter vLLM/llama-server
  déjà compilés, jamais pour l'étape de build de l'installeur.

### Comparaison sur cinq critères

| Critère | Natif Windows | WSL2 | Docker complet (sur WSL2) |
|---|---|---|---|
| **Effort de portage** | Le plus élevé. Réécriture des 4 scripts shell (PowerShell/batch), correctif Rust dans `lib.rs` (`find_python`, nettoyage cache — zone 4), ~20 chemins `bin/python` (zone 2), signaux SIGKILL→psutil (zone 2), branche Windows dans `installer.py` (MSVC+nvcc). | Faible à modéré. Les scripts bash s'exécutent tels quels dans la distro Linux ; le code Python et Rust n'a pas besoin de branches Windows puisqu'il tourne sous un vrai noyau Linux. Reste à gérer : l'app Tauri elle-même doit rester un exécutable Windows natif qui lance un backend *dans* WSL2 (aller-retour réseau localhost Windows↔WSL2), ou tourner entièrement dans WSL2 avec affichage via WSLg. | Modéré. Pas de portage du code Python/Rust (tourne en conteneur Linux), mais écriture de la composition (services, volumes, exposition GPU — décrite en Partie 3) et adaptation de l'installeur pour qu'il n'ait plus à compiler sur la machine hôte. |
| **Fonctionnalités perdues** | Aucune en théorie une fois porté ; presse-papiers, notifications, tray icon Tauri natifs Windows fonctionnent nativement (`arboard` supporte déjà Windows, zone 4). | Le presse-papiers (`arboard`/`wl-paste`, zone 4) et l'intégration système (barre des tâches, notifications natives) sont dégradés ou nécessitent WSLg ; latence réseau localhost supplémentaire entre l'UI Windows et le backend WSL2 si architecture hybride. | Perte quasi totale de l'intégration desktop : pas de fenêtre Tauri native depuis un conteneur sans réintroduire une architecture hybride (UI hors conteneur, backend + inférence dedans) — revient à un sous-cas de WSL2 avec une couche de composition en plus. |
| **Performance d'inférence GPU** | Native — accès direct au pilote CUDA Windows, aucune couche de virtualisation. Référence. | Quasi native pour le calcul (GPU-PV a un surcoût mesuré généralement faible pour du calcul soutenu type inférence LLM, contrairement à des charges à forte latence d'appels), mais copie mémoire hôte↔WSL2 additionnelle possible selon le pipeline. | Identique à WSL2 pour le calcul (le conteneur tourne dans la même distro WSL2), avec une couche d'indirection Docker supplémentaire négligeable pour de l'inférence longue durée. |
| **Complexité d'installation utilisateur final** | La plus faible *si* l'installeur graphique est effectivement porté (promesse README zone 7) — un `.msi`/`.exe` unique. La plus élevée si le portage reste partiel : compilation manuelle MSVC/CUDA hors de portée d'un utilisateur non technique. | Élevée : suppose l'activation de WSL2, l'installation d'une distro, la configuration du pilote NVIDIA côté Windows sans installer de pilote Linux (piège documenté, zone Partie 2 ci-dessus) — plusieurs étapes manuelles hors du contrôle d'EchoHub. | La plus élevée des trois : Docker Desktop + WSL2 + NVIDIA Container Toolkit + image `devel` de plusieurs Go à télécharger avant le premier lancement. |
| **Coût de maintenance à deux têtes (Linux + Windows)** | Le plus élevé : deux jeux de scripts, deux branches de compilation dans `installer.py`, tests réels sur deux OS à chaque changement des moteurs d'inférence. | Modéré : le code applicatif reste unique (Linux dans les deux cas) ; seule la coquille Tauri et les scripts d'orchestration de premier niveau divergent. | Le plus faible sur le code (Dockerfile+compose partagés entre développeurs Linux et Windows, un seul environnement d'exécution testé), mais un coût ajouté propre : maintenir l'image et sa taille au fil des mises à jour CUDA/vLLM. |

**Lecture rapide** : le natif Windows maximise l'intégration et la performance mais coûte le plus cher à
porter et à maintenir dans la durée face à Linux. WSL2 est le compromis le plus rapide à obtenir un résultat
fonctionnel (le code ne bouge presque pas) mais dégrade l'expérience desktop et garde une dépendance de
configuration système fragile côté utilisateur. Docker sur WSL2 uniformise la maintenance mais alourdit
l'installation et complique structurellement l'intégration desktop Tauri — verdict détaillé et recommandation
en Partie 3.

---

## Partie 3 — Recommandation et plan de mise en œuvre

### Voie recommandée : portage natif Windows

EchoHub est une application desktop Tauri destinée à un usage personnel sur un poste unique — pas un service
multi-utilisateurs à opérer. Docker et WSL2 dégradent tous deux l'intégration desktop que Tauri existe
justement pour fournir (presse-papiers, tray, fenêtre native), pour un gain de portage qui s'avère plus
faible qu'il n'y paraît : la Partie 1 a montré que le backend Python (zone 2), la couche données (zone 5,
`get_user_data_dir()` gère déjà `%APPDATA%`) et le serveur MCP (zone 3) sont déjà largement portables ; ce
qui bloque est concentré et mécanique (chemins venv, signaux, un fichier Rust), à l'exception d'un seul point
réellement structurant — la compilation de `llama-cpp-python` sous MSVC/CUDA dans `installer.py`. Le natif
Windows est la seule voie cohérente avec la promesse produit du README (« no terminal access after the first
install ») et avec la performance GPU maximale attendue d'une RTX 5090. Le coût de double-maintenance
Linux/Windows existe dans les trois voies dès qu'on veut réellement du natif desktop des deux côtés ; autant
qu'il finance de la performance et de l'intégration plutôt qu'une couche de virtualisation supplémentaire.
WSL2 reste une option de repli rapide pour un prototype de validation technique (lot 0 ci-dessous s'appuie
dessus), pas pour la version livrée.

Docker n'étant pas la voie recommandée, aucune composition de services/volumes/image de base n'est décrite
ici (conforme au mandat, qui ne le demande qu'en cas de recommandation Docker).

### Plan de mise en œuvre en lots ordonnés

**Portage mécanique — exécution directe, pas de décision d'architecture :**

| Lot | Contenu | Effort | Risque |
|---|---|---|---|
| 1 | Chemins venv : fonction utilitaire centrale `venv_python()`/`venv_pip()` bifurquant sur `os.name`, substituée aux ~20 occurrences `bin/python` recensées zone 2 (`vllm_service.py`, `vllm_manager.py`, `installer.py`, `mcp_manager.py`, `engine_router.py`, `finetune_service.py` déjà correct à répliquer) + suffixe `.exe` sur `llama-server` (zone 6, `llama_server_config.py:28`). | 4 h | Faible — mécanique, testable unitairement sans machine Windows. |
| 2 | Gestion de processus : remplacer les foyers `os.kill`/`signal.SIGKILL` par `psutil` (déjà une dépendance) dans `vllm_process.py:37-46`, `llama_server_service.py:66-74`, `mcp_manager.py:606-609`, `connectors.py:244-249` ; remplacer `start_new_session=True` par une branche `creationflags=CREATE_NEW_PROCESS_GROUP` sous Windows dans `vllm_service.py:290` et `llama_server_service.py:156`. | 3 h | Faible-moyen — logique claire, mais le comportement réel de kill/respawn doit être vérifié par un test réel, pas seulement relu. |
| 3 | Pidfile `/tmp/echohub_vllm.pid` (`vllm_process.py:14`) → `tempfile.gettempdir()`. | 0,5 h | Faible. |
| 4 | Réécriture des scripts d'orchestration en PowerShell (`start.ps1`, `stop.ps1`, `restart.ps1`, `build.ps1`) : détection OS Windows, `winget`/`choco` pour les dépendances système, `rustup-init.exe`, script d'installation Bun PowerShell dédié, `taskkill /PID /F` au lieu de `pkill`. | 8 h | Moyen — dépend de la disponibilité réelle de `winget` sur la machine cible et du comportement des installeurs tiers (Rust, Bun) invoqués depuis PowerShell. |
| 5 | Code Rust Tauri (`lib.rs`) : `find_python()` réécrit avec `Path::is_absolute()` et `std::env::consts::EXE_SUFFIX` au lieu de `starts_with('/')` et `which` codé en dur (zone 4) ; nettoyage du cache bytecode via une marche de répertoire native (`std::fs::read_dir` récursif ou crate `walkdir`) au lieu du binaire `find`. Nécessite recompilation complète de la coquille. | 4 h | Moyen — code compilé, erreurs seulement visibles à la recompilation/exécution Windows réelle. |
| 6 | `tauri.conf.json` : ajouter les cibles `"msi"`/`"nsis"` à `bundle.targets` (l'icône `.ico` existe déjà) ; corriger `beforeDevCommand` avec `cross-env` pour la portabilité de la syntaxe de variable d'environnement. | 2 h | Faible. |
| 9 | Résolution des launchers MCP `npx`/`node` via `shutil.which()` (gère `PATHEXT`) dans `mcp_manager.py:86` au lieu d'un appel direct — corrige le piège `FileNotFoundError` documenté zone 3. | 2 h | Faible — priorité basse, uniquement nécessaire si des connecteurs MCP JavaScript communautaires sont utilisés. |
| 10 | Documentation : retirer ou nuancer `README.md:49` (« Windows (WSL2) ») tant que le portage natif n'est pas validé, ajouter une section Windows réelle une fois les lots précédents faits, compléter `docs/llama-server.md` d'un paragraphe Windows (chemin `%USERPROFILE%\.unsloth\...`, suffixe `.exe`). | 2 h | Faible. |

**Décisions d'architecture — arbitrage requis avant exécution, pas de correctif mécanique évident :**

| Lot | Contenu | Effort | Risque |
|---|---|---|---|
| 0 | Validation empirique préalable sur la machine cible réelle (RTX 5090, Windows 10/11, CUDA 12.8+ installé) : `vllm==0.21.0` charge-t-il un modèle AWQ sans erreur de kernel ? `flash-attn`/llama.cpp compilent-ils et tournent-ils sur un modèle head_dim > 128 (ex. Qwen3.5-9B) sans crash, même en repli FA2 ? Ce lot conditionne le dimensionnement réel des lots 7 et 8. | 2 h | Faible en soi, mais bloquant informationnellement — à faire en premier. |
| 7 | Brancher `installer.py` (`_compile_llama_async`) pour Windows : détection de Visual Studio Build Tools / MSVC, résolution de `CUDA_PATH` (posé automatiquement par l'installeur NVIDIA, à vérifier), `CMAKE_ARGS` adapté au générateur MSVC plutôt qu'à Makefiles Unix. Décision à trancher : embarquer un sous-ensemble de toolchain dans l'installeur EchoHub (lourd, plus fiable pour l'utilisateur final) ou exiger que Visual Studio Build Tools soit pré-installé (plus léger, casse la promesse « no terminal access »). | 10 h (+ itérations de compilation réelles) | Élevé — dépend de configurations MSVC/CUDA variables d'une machine à l'autre ; seule une machine Windows réelle permet de trancher. |
| 8 | Si le lot 0 révèle un échec de `vllm==0.21.0` sur sm_120 : décision entre (a) faire évoluer la version pour la cible Windows uniquement (double pin par OS, coût de maintenance accru) ou (b) attendre/adopter une version plus récente pour les deux OS (risque de régression Linux à re-tester). | 6 h + itérations | Élevé — dépend d'un résultat externe (comportement réel de vLLM sur ce matériel) non garanti par la littérature actuelle. |
| 11 | Validation end-to-end complète sur machine Windows réelle : lancement de l'app, chargement d'un modèle sur chacun des trois moteurs, conversation, connecteur MCP. Ce lot peut faire remonter des correctifs dans n'importe lequel des lots précédents. | 6 h | Le vrai filet de sécurité du plan — à ne jamais sauter au profit d'une relecture de code. |

**Total estimé : ~49,5 heures**, dont ~16 h de décisions d'architecture à haut risque (lots 0, 7, 8) et
~33,5 h de portage mécanique à risque faible-moyen. Ordre d'exécution recommandé : lot 0 en tout premier
(il dimensionne 7 et 8), puis lots 1-3-9-10 (mécaniques, sans dépendance machine Windows), puis 4-5-6
(nécessitent un environnement Windows de test), puis 7-8 en parallèle si deux personnes, puis 11 en clôture
obligatoire.

---

## VRAM : 32 Go vs 12 Go

32 Go permettent de charger sans quantification agressive des modèles jusqu'à ~30-35B de paramètres en
Q4/Q5 GGUF ou AWQ (contre ~7-9B confortablement sur 12 Go), et d'ouvrir des fenêtres de contexte nettement
plus longues à VRAM égale allouée au KV-cache (le `DEFAULT_CTX = 131072` déjà présent dans `mcp_server.py:32`
devient réellement exploitable en pratique, pas seulement configurable).

32 Go rendent aussi possible ce que 12 Go interdisaient structurellement : faire cohabiter en VRAM le modèle
de chat principal et un second modèle (embedding pour la mémoire ChromaDB, modèle de fine-tuning en test,
ou un second moteur d'inférence en parallèle) sans devoir décharger l'un pour charger l'autre à chaque
changement de tâche.
