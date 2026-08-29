# ARBORESCENCE — EchoHub v2

*Dernière mise à jour : 2026-08-29 — 188 fichiers Python (backend), 4 (atelier), 207 fichiers
frontend.*

Organisation **par domaine métier**, jamais par couche technique : la structure dit ce que le
produit fait, pas avec quoi il est bâti. Un domaine expose son interface publique (`__init__.py`
côté Python, `index.ts` côté TypeScript) et n'est jamais atteint par ses internes.

## Racine

| Fichier | Rôle |
|---|---|
| `README.md` | Ce qu'est le produit, lancement, ports, sécurité |
| `ARCHITECTURE.md` | Carte des domaines et définition non ambiguë de chaque dossier |
| `ARBORESCENCE.md` | Ce fichier |
| `STATE.md` | État courant, décisions et leurs raisons |
| `TODO.md` | Ce qui reste, par priorité |
| `COMPATIBILITE-GPU.md` | Contraintes GPU payées en pannes réelles — CUDA, WSL2, débits mesurés |
| `DESIGN.md` | Langage visuel : palette sémantique, typographie, mouvement |
| `MESURES-MOE.md` | Relevés sur les modèles à experts |
| `BENCH-QWEN38-27B.md` | Banc d'essai Qwen3.8-27B, build llama.cpp dédié |
| `PREUVES-MULTIMODAL.md` | Coût en tokens d'une image et repli sans tour de vision |
| `PLAN-EXECUTION.md` | Plan des lots, avec les sections référencées depuis le code |
| `Dockerfile` | Image GPU — CUDA 12.8 devel, recompilation de `llama-cpp-python` |
| `docker-compose.yml` | Orchestration : `echohub`, `searxng`, `echohub-atelier` ; syntaxe GPU **inversée** entre WSL2 et Linux natif |
| `.gitattributes` | `* text=auto eol=lf` — sans lui, un checkout Windows casse l'entrypoint |
| `start.sh` `stop.sh` `restart.sh` | Cycle de vie, PID de groupe et journaux remis à zéro |
| `acces-distant.ps1` | Accès distant par Tailscale — réseau privé, rien d'exposé. Droits administrateur requis |
| `.env.example` | Variables attendues, sans valeurs sensibles. **Le port réel vient du `.env`** |
| `InterfaceAcces.txt` | Adresse d'accès locale courante |

## backend/ — 188 fichiers Python

### `core/` (5) — socle partagé, aucun métier

`config.py` réglages pydantic (dont `atelier_*`) · `db.py` SQLite WAL, schéma et migrations
additives idempotentes · `errors.py` erreurs métier portant code, statut HTTP et remédiation ·
`logging.py` loguru.

### `system/` (9) — ce que la machine offre

`gpu.py` · `nvml.py` mesure par NVML · `nvidia_smi.py` repli · `memoire.py` · `plateforme.py`
contraintes WSL2 / Linux natif · `profil.py` agrégat · `modeles.py` · `api.py`. Une valeur non
mesurable vaut `null`, jamais une estimation.

### `models/` (23) — trouver, télécharger, **connaître** les modèles

`gguf_reader.py` analyse binaire de l'en-tête · `gguf_metadata.py` interprétation et poids réel des
tenseurs · `gguf_types.py` · `safetensors_reader.py` index des poids · `coherence.py` confronte le
déclaré au présent · `discovery.py` recherche Hub · `capacites.py` capacités **déduites** des
annonces, tracées · `registry.py` index local · `disque.py` inventaire de ce qui occupe, y compris
le non chargeable · `storage.py` dont `fichiers_projecteurs()` (détection `mmproj*.gguf`) ·
`download.py`, `download_worker.py`, `download_selection.py`, `download_journal.py` transferts,
reprise, parts multiples · `api.py`.

### `inference/` (56) — décider, appliquer, générer

| Fichier | Rôle |
|---|---|
| `planner/` (11) | **Pur et testable sans GPU** : `budget.py`, `paliers.py`, `postes_memoire.py`, `experts.py` (MoE), `environnement.py`, `reglages.py`, `entrees.py`, `plan.py`, `moteur.py`, `planificateur.py` — plan justifié, dégradation strictement conservatrice |
| `engines_adapters/` (15) | Application réelle : `adaptateur_llama_cpp.py` (bindings), `adaptateur_llama_server.py` (binaire natif, HTTP), `adaptateur_vllm.py`, `processus_llama_server.py` et `processus_vllm.py` (pilotage des sous-processus), `superviseur.py` (un modèle à la fois), `traduction_plan.py`, `diagnostic.py` qualifié, `journal.py`, `vram.py`, `experts_hote.py`, `flux.py` (pont flux bloquant → asynchrone), `contrat.py`, `base.py` |
| `__init__.py` | Interface publique et **transport** de la boucle d'outils |
| `harnais.py` | Conduite de la boucle : tours, relances, budget, détection de radotage |
| `harnais_outils.py` | Mise en forme du flux d'outils : balises affichées, aperçus d'arguments, compaction de l'historique, retrait du balisage d'appel avant renvoi au moteur |
| `reprise.py` | Reprise d'une réponse coupée par la fenêtre : bornes, marge, consignes, avertissement |
| `api.py` | Routes `/inference` — dont `/contexte`, qui compacte avant de compter |

### `chat/` (20) — conversations, branches, génération

`depot.py` persistance · `branches.py` arbre de messages, édition non destructive · `generation.py`
assemblage du contexte et du prompt système · `annulation.py` état d'une génération en cours ·
`port_inference.py` contrat attendu du moteur, défini côté consommateur ·
`adaptation_inference.py` branchement du domaine voisin · `flux_sse.py` · `erreurs.py` ·
`modeles.py` · `routes.py`.

### `outils/` (29) — le harnais du modèle

| Fichier | Rôle |
|---|---|
| `contrat.py` | Forme d'un outil, de son résultat, `EchecOutil`, et **normalisation des alias d'arguments** |
| `registre.py` | Outils disponibles, ordre de présentation (celui de la boucle de travail), familles de l'écran de sélection, exécution d'un appel |
| `socle.py` | Prompt système posé **avant** celui de la conversation — en anglais |
| `recherche_web.py` · `recuperer_page.py` | Recherche, puis lecture d'une page — la seconde moitié de la première |
| `fichiers_bac.py` | `ecrire_fichier`, `lire_fichier`, `modifier_fichier` |
| `explorer_bac.py` | `lister_fichiers`, `chercher_dans_fichiers` — voir avant d'agir |
| `executer_python.py` · `executer_commande.py` | Exécution réelle, déléguée à l'atelier |
| `atelier.py` | Client HTTP de l'atelier : jeton, appels, erreurs qualifiées |
| `bac_a_sable.py` | **Pont** : traduit le `racine_bac` d'une conversation en sous-dossier de l'atelier, délègue, replie proprement. N'exécute plus rien lui-même |
| `balayage_bac.py` | Enregistre dans le magasin `fichiers` ce que l'atelier a produit de nouveau |
| `presenter_fichier.py` | Le modèle désigne un fichier existant, l'utilisateur le voit en carte cliquable |
| `creer_artefact.py` | Produit un artefact versionné ; le numéro de version dérive du magasin de fichiers (`<id>-vN.<ext>`), seule source qui survive à un redémarrage |
| `api.py` | Routes `/outils` |

### `fichiers/` (17) — magasin des pièces jointes et des productions

`politique.py` quotas et types acceptés · `stockage.py` racines par conversation · `depot.py`
persistance · `service.py` dépôt, liaison au message, et `resoudre_reference()` qui accepte un
identifiant **ou** un nom affiché, borné à la conversation · `erreurs.py` · `modeles.py` ·
`routes.py`.

### `engines/` (14) — installation et santé des moteurs

`_sonde.py` et `llamacpp/sonde.py`, `vllm/sonde.py` : sondes réelles (importable **et** capable de
toucher le GPU) · `vllm/venvs.py` venvs versionnés · `vllm/installation.py` et `vllm/etat.py` flux
d'installation en SSE · `llamacpp/diagnostic.py` · `_processus.py` · `service.py` · `api.py`.

### `recherche/` (14) — recherche web locale

`client_searxng.py` · `analyse.py` · `cache.py` · `pool_moteurs.py` · `service.py` ·
`erreurs.py` · `modeles.py` · `api.py` dont la sonde `/recherche/sante`.

## atelier/ — 4 fichiers

Conteneur de dev persistant, unique, partagé par toutes les conversations.

| Fichier | Rôle |
|---|---|
| `serveur.py` | Service HTTP FastAPI : exécute commandes et code dans `/workspace/<conversation>`, gardé par `ATELIER_JETON` (repli fermé : sans jeton, refus) |
| `Dockerfile` | Ubuntu 24.04, toolchain, **sans `nasm`** — c'est le cas de preuve de l'installation par l'agent |
| `requirements.txt` | Dépendances du service |
| `README.md` | Ce que l'atelier garantit, et ce qu'il ne garantit pas |

## frontend/src/ — 207 fichiers

| Dossier | Rôle |
|---|---|
| `App.tsx` | Navigation, bandeau d'état, éjection — seul point de rencontre des domaines |
| `cible/` | Croise métadonnées lues, profil machine et moteurs pour bâtir une cible de chargement |
| `chat/conversation/` | Fil, composeur, liste des conversations, pièces jointes, panneau et catalogue d'outils, sélection persistée, `demo/` écran de démonstration |
| `chat/markdown/` | Analyseur maison (parseur, inline, listes, tableaux, coloration) — aucun HTML injecté |
| `chat/raisonnement/` | Extraction du raisonnement, lecture d'appel d'outil, cartes d'outil, conventions de balisage |
| `chat/artefacts/` | Détection, versions, cartes, modale, panneau, `useAtelier.ts` et `fournisseur-atelier.tsx` |
| `chat/actions/` | Survol, navigation de branches, édition en place, copie, gestes |
| `chat/plan/` | Plan de chargement rendu lisible : ruban de couches, barres mémoire, arbitrage du contexte, justifications, réglages de cache KV |
| `chat/contexte/` | Occupation de la fenêtre, postes, panneau |
| `chat/reglages/` | Réglages de conversation : champs, plafond de réponses, séquences d'arrêt, mesures |
| `chat/api/` | Client du domaine chat : conversations, branches, fichiers, flux de génération, limites |
| `models/` | `recherche/` Hub, filtres et capacités déduites · `locaux/` registre, dossiers non inscrits, inventaire disque · `telechargements/` · `faisabilite/` verdict VRAM · `api/` |
| `system/` | `materiel/` barres mémoire et profil machine · `contraintes/` · `moteurs/` cartes, installation vLLM · `api/` |
| `shared/design/` | Primitives (`Button`, `Card`, `Badge`, `Slider`, `Progress`, `Tooltip`), `Modal.tsx` et `Feuille.tsx` (modale et tiroir, sans débordement), `MenuContextuel.tsx`, `BoutonActions.tsx`, `useEstGrandEcran.ts` et `useHauteurVisuelle.ts` (points de rupture et clavier mobile), tokens, tons, `motion.ts`, polices IBM Plex versionnées |
| `shared/api/` | Client unique, transport, SSE, erreurs, et types miroirs du backend (`types-chat`, `types-inference`, `types-modeles`, `types-moteurs`, `types-plan`, `types-systeme`) |

`frontend/captures/` — 13 captures de l'interface (bureau et mobile), servant la documentation.

## docker/

| Fichier | Rôle |
|---|---|
| `nginx.conf` | Sert le build statique, proxifie `/api` en retirant le préfixe, applique l'authentification HTTP |
| `entrypoint.sh` | Lance uvicorn et nginx, neutralise la mémoire unifiée sous WSL2, **appose une empreinte de version aux assets**, engendre `.htpasswd` quand `ECHOHUB_AUTH_USER`/`HASH` sont présents |
| `outils-acces.py` | Engendre les identifiants web — mot de passe affiché une fois, seule l'empreinte crypt salée est conservée |
| `cdi/` | `echohub-cdi-regenerer` et `echohub-cdi.service` : régénèrent le spec CDI NVIDIA au boot. Un spec vieux de 18 jours a fait échouer tout chargement GPU après un reboot (voir `STATE.md`, 2026-08-28) |
| `searxng/settings.yml` | Configuration de la recherche — format JSON activé, limiteur désactivé |
| `preuves_bac_a_sable.py` | Preuves d'isolation de l'ancien bac confiné, exécutées en conteneur. **Antérieur à l'atelier** : conservé comme trace de ce qui a été mesuré, il ne décrit plus le chemin d'exécution courant |

## Tests — 442 fonctions Python, 4 suites TypeScript

Sans GPU ni réseau.

`backend/inference/planner/tests/` · `backend/inference/tests/` (contexte d'exécution, pièces
jointes, réémission d'outils, compaction de l'historique, boucle d'appels ratés) ·
`backend/inference/engines_adapters/tests/` (dialectes d'appel d'outil, multimodal) ·
`backend/models/tests/` · `backend/chat/tests/` (dont survie de la génération sans client,
migrations) · `backend/fichiers/tests/` (dont résolution de référence) · `backend/outils/tests/`
(contrat du pont atelier, client HTTP, balayage, outils de fichier, socle, présentation, alias
d'arguments) · `backend/recherche/tests/`.

Deux domaines n'ont **aucun test** : `system/` et `engines/`. Ce n'est pas un oubli d'écriture de
cette page — ils touchent NVML, le GPU et l'installation de venvs, donc rien qui se teste sans la
machine. Le noter plutôt que le laisser deviner.

Côté TypeScript, quatre suites pures, sans framework ni navigateur — chacune s'exécute par
`bun run <fichier>` et sort en code non nul s'il reste un échec :
`chat/markdown/tests/parseur.test.ts` · `chat/raisonnement/tests/extraction.test.ts` et
`lecture-appel.test.ts` · `chat/artefacts/tests/versions.test.ts`.

**Lancer la suite Python sans toucher au conteneur en service** — le venv vit dans `backend/.venv`,
monter tout `backend` l'écraserait :

```bash
docker run --rm --gpus all --entrypoint /app/backend/.venv/bin/python \
  -v "$PWD/backend/inference:/app/backend/inference" \
  -v "$PWD/backend/outils:/app/backend/outils" \
  echohub:v2 -m pytest backend -q
```
