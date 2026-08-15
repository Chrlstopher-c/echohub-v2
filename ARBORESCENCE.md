# ARBORESCENCE — EchoHub v2

*Dernière mise à jour : 2026-08-15 — 321 fichiers suivis*

Organisation **par domaine métier**, jamais par couche technique : la structure dit ce que le
produit fait, pas avec quoi il est bâti. Un domaine expose son interface publique (`__init__.py`
côté Python, `index.ts` côté TypeScript) et n'est jamais atteint par ses internes.

## Racine

| Fichier | Rôle |
|---|---|
| `ARCHITECTURE.md` | Carte des domaines et définition non ambiguë de chaque dossier |
| `COMPATIBILITE-GPU.md` | Contraintes GPU payées en pannes réelles — CUDA, WSL2, débits mesurés |
| `DESIGN.md` | Langage visuel : palette sémantique, typographie, mouvement |
| `STATE.md` | État courant, décisions et leurs raisons |
| `TODO.md` | Ce qui reste, par priorité |
| `README.md` | Lancement manuel, stack, ports |
| `Dockerfile` | Image GPU — CUDA 12.8 devel, recompilation de llama-cpp-python |
| `docker-compose.yml` | Orchestration ; syntaxe GPU **inversée** entre WSL2 et Linux natif |
| `start.sh` `stop.sh` `restart.sh` | Cycle de vie, PID et journaux |
| `.env.example` | Variables attendues, sans valeurs sensibles |

## backend/ — 118 fichiers

### `core/` (5) — socle partagé, aucun métier

`config.py` réglages pydantic · `db.py` SQLite WAL, schéma et migrations additives idempotentes ·
`errors.py` erreurs métier portant code, statut HTTP et remédiation · `logging.py` loguru.

### `system/` (9) — ce que la machine offre

Mesure réelle : GPU par NVML avec repli `nvidia-smi`, mémoire, contraintes de plateforme. Une
valeur non mesurable vaut `null`, jamais une estimation.

### `models/` (22) — trouver, télécharger, **connaître** les modèles

`gguf_reader.py` analyse binaire de l'en-tête · `gguf_metadata.py` interprétation et mesure du
poids réel des tenseurs · `safetensors_reader.py` index des poids · `coherence.py` confronte le
déclaré au présent · `discovery.py` recherche Hub · `capacites.py` capacités **déduites** des
annonces, tracées · `registry.py` index local · `disque.py` inventaire de ce qui occupe, y compris
le non chargeable · `download*.py` transferts, reprise, parts multiples · `api.py` routes.

### `inference/` (34) — décider, appliquer, générer

`planner/` **pur et testable sans GPU** : budget mémoire, paliers, plan justifié, dégradation
strictement conservatrice, gestion des experts MoE · `engines_adapters/` application réelle :
adaptateurs llama.cpp et vLLM, superviseur (un modèle à la fois), diagnostic qualifié, journal,
mesure VRAM, pont flux bloquant → asynchrone · `__init__.py` interface publique **et boucle
d'outils** · `api.py` routes.

### `chat/` (19) — conversations, branches, génération

`depot.py` persistance · `branches.py` arbre de messages, édition non destructive · `generation.py`
assemblage du contexte et du prompt système · `port_inference.py` contrat attendu du moteur, défini
côté consommateur · `adaptation_inference.py` branchement du domaine voisin · `flux_sse.py` ·
`routes.py`.

### `outils/` (5) — le harnais

`contrat.py` forme d'un outil et de son résultat · `registre.py` outils disponibles et exécution ·
`socle.py` prompt système posé **avant** celui de la conversation · `recherche_web.py` premier
outil, adossé au domaine `recherche`.

### `engines/` (14) — installation et santé des moteurs

Sondes réelles (importable ET capable de toucher le GPU), venvs vLLM versionnés, flux
d'installation en SSE.

### `recherche/` (10) — recherche web locale

Client SearXNG, analyse, service, sonde de disponibilité.

## frontend/src/ — 168 fichiers

| Dossier | Rôle |
|---|---|
| `App.tsx` | Navigation, bandeau d'état, éjection — seul point de rencontre des domaines |
| `cible/` (3) | Croise métadonnées lues, profil machine et moteurs pour bâtir une cible de chargement |
| `chat/` (79) | `conversation/` fil et composeur · `markdown/` analyseur maison, aucun HTML injecté · `raisonnement/` extraction et repli des blocs · `actions/` survol, branches, édition · `reglages/` · `plan/` · `contexte/` occupation de la fenêtre · `api/` |
| `models/` (27) | `recherche/` Hub et filtres de capacités · `locaux/` registre, favoris, inventaire disque · `telechargements/` · `faisabilite/` verdict VRAM |
| `system/` (19) | Matériel, contraintes, moteurs, installation vLLM |
| `shared/` (38) | `design/` primitives, tokens, menu contextuel, polices IBM Plex versionnées · `api/` client unique, SSE, types miroirs du backend |

## docker/

`nginx.conf` sert le build statique et proxifie `/api` en retirant le préfixe · `entrypoint.sh`
lance uvicorn et nginx, neutralise la mémoire unifiée sous WSL2, **appose une empreinte de version
aux assets** · `searxng/settings.yml` configuration JSON de la recherche.

## Tests

`backend/inference/planner/tests/` · `backend/models/tests/` · `backend/chat/tests/` ·
`backend/recherche/tests/` · `backend/inference/engines_adapters/tests/` ·
`frontend/src/chat/markdown/tests/` · `frontend/src/chat/raisonnement/tests/`

**196 tests Python verts**, sans GPU ni réseau.
