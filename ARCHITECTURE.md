# Architecture — EchoHub v2

## Périmètre

| Domaine | Ce qu'il fait |
|---|---|
| `system` | Détecte matériel et plateforme : GPU, VRAM, RAM, WSL2 ou Linux natif, pilote |
| `engines` | Installe et gère llama.cpp et vLLM, leurs versions et venvs |
| `models` | Cherche sur Hugging Face, télécharge, lit les métadonnées GGUF, tient le registre local |
| `inference` | **Planificateur de chargement** + pilotage des moteurs + génération + harnais d'outils |
| `chat` | Conversations, branches, streaming des réponses, persistance |
| `outils` | Les outils du modèle : fichiers, exécution, recherche, artefacts — et le pont vers l'atelier |
| `fichiers` | Magasin des pièces jointes et des productions, rattachées à une conversation |
| `recherche` | Recherche web par instance SearXNG locale |

**Hors périmètre, volontairement** — à ne pas commencer, à ne pas préparer « au cas où » : RAG et
ChromaDB, skills MCP, connecteurs (Discord), fine-tuning.

La recherche web faisait partie de cette liste au cadrage du MVP. Elle en est sortie le 2026-08-15,
quand le harnais d'outils a rendu la citation de sources possible : SearXNG est depuis un service
actif par défaut dans `docker-compose.yml` (jamais publié, `expose` seul), et le domaine `recherche`
est complet. `echohub` ne le déclare volontairement pas en `depends_on` — le backend doit démarrer et
servir même si la recherche est indisponible, auquel cas le domaine rend un 503 explicite et la
sonde `/api/recherche/sante` dit ce qui a été mesuré.

## Le cœur : le planificateur de chargement

C'est la raison d'être de la v2. Un module unique, **seule source de vérité**, qui répond à une
question : *comment charger ce modèle sur cette machine, maintenant ?*

```
plan = planifier(chemin_modele, preferences_utilisateur)
  → couches_gpu, contexte, batch, type_kv_cache, moteur, variables d'environnement
  → plus la justification de chaque valeur, affichable à l'utilisateur
```

Il **mesure** au lieu de supposer :

1. métadonnées réelles du GGUF — architecture, `block_count`, taille sur disque ;
2. VRAM et RAM réellement libres au moment du chargement ;
3. plateforme et ses contraintes (voir `COMPATIBILITE-GPU.md`) ;
4. préférences explicites de l'utilisateur, **plafonnées** par ce que la machine permet.

Trois règles qui viennent directement des défauts mesurés sur la v1 :

- **Aucune constante magique.** Pas de « 150 Mo par couche », pas de paliers de paramètres. Toute
  valeur vient d'une lecture ou d'une mesure.
- **Aucune duplication.** Le frontend affiche le plan, il ne le recalcule jamais. Un seul endroit
  décide, partout.
- **Dégradation, jamais escalade.** Un échec produit un plan plus conservateur, jusqu'à un mode
  minimal garanti de fonctionner.

Le planificateur doit être **testable sans GPU** : on lui injecte des métadonnées et un budget
mémoire, on vérifie le plan produit. C'était impossible en v1, d'où les défauts non détectés.

## Structure — par domaine, jamais par couche technique

```
backend/
  system/      détection matériel et plateforme
  engines/     installation et versions de llama.cpp et vLLM
  models/      recherche, téléchargement, métadonnées GGUF, registre
  inference/   planificateur, adaptateurs de moteurs, génération, harnais d'outils
  chat/        conversations, branches et persistance
  outils/      outils du modèle (fichiers, exécution, recherche, artefacts) + pont vers l'atelier
  fichiers/    magasin des pièces jointes et des productions
  recherche/   client SearXNG, analyse, cache
  core/        config, logging, erreurs, base de données
atelier/       conteneur d'exécution root persistant (Dockerfile, serveur HTTP, README)
frontend/src/
  models/      écrans de découverte et gestion des modèles
  chat/        écran de conversation : fil, plan, contexte, outils, artefacts, réglages
  system/      matériel, contraintes, moteurs
  cible/       croisement métadonnées × machine × moteurs pour bâtir une cible de chargement
  shared/      design system, composants, client API
```

Chaque domaine expose une interface publique. Un domaine n'importe jamais les internes d'un autre.

## L'atelier d'exécution — une frontière de conteneur, pas un bac dans le backend

Les outils `executer_commande` et `executer_python` (domaine `outils`) n'exécutent plus rien dans le
backend. L'exécution vit dans un **conteneur de dev séparé et persistant**, `echohub-atelier`
(dossier `atelier/` à la racine : `Dockerfile`, `serveur.py`, `README.md`). L'agent y est **root**,
avec réseau, PATH complet et toolchain ; il installe ce qui lui manque (`apt`, `pip`), et fichiers
comme paquets **persistent**.

Pourquoi ce déplacement : l'ancien confinement (`setuid` + `rlimits` + PATH minimal, dans
`bac_a_sable.py`) protégeait l'hôte au prix de rendre l'outil inerte dès qu'il fallait installer quoi
que ce soit (mesuré : `nasm: command not found`). Le confinement n'a pas disparu, il s'est **déplacé
vers la frontière du conteneur** : aucun chemin de l'hôte monté, aucun `docker.sock`, ressources
bornées par Compose (`mem_limit`, `cpus`, `pids_limit`).

**Mécanisme d'exécution — HTTP interne, pas `docker.sock`.** Le backend parle à l'atelier par un
petit service HTTP (`atelier/serveur.py`, FastAPI), sur le réseau interne de la pile (port **jamais
publié**), gardé par un jeton partagé (`ATELIER_JETON`). Le client backend est
`backend/outils/atelier.py` ; `backend/outils/bac_a_sable.py` n'est plus qu'un pont qui traduit le
`racine_bac` d'une conversation en dossier de l'atelier et délègue. Monter `docker.sock` dans le
backend aurait donné root sur l'hôte à un backend qui exécute du texte de modèle — écarté pour cette
raison.

**Workspace partagé.** Un volume nommé (`echohub_ateliers`) est monté dans le backend
(`/data/ateliers`, = `settings.atelier_workspace`) **et** dans l'atelier (`/workspace`). Le `racine_bac`
d'une conversation est `atelier_workspace/<conversation_id>` ; l'atelier le voit sous
`/workspace/<conversation_id>`. C'est le même dossier : un fichier écrit par `ecrire_fichier` (backend)
est vu du shell de l'atelier, et un fichier produit par une commande de l'atelier est balayé
(`balayage_bac.py`) et rattaché à la conversation comme pièce jointe (`origine='modele'`).

**Repli.** Atelier injoignable → les outils rendent un message actionnable (« démarrer avec
`docker compose up -d echohub-atelier` »), journalisé (loguru), jamais un timeout muet ni un crash.

## Stack

- **Backend** : Python 3.10, FastAPI, uvicorn, pydantic, loguru. Python est imposé par
  `llama-cpp-python` et vLLM, pas choisi.
- **Frontend** : React 18, TypeScript strict, Tailwind, Framer Motion.
- **Livraison** : Docker, nginx sert le frontend statique et proxifie `/api`.
- **Typage** : zéro `any`, types de retour explicites sur toute fonction publique.

`tsc` doit passer. La v1 avait trois erreurs TypeScript jamais vues parce que `bun run dev`
n'exécute pas `tsc` — le build de production les contournait au lieu de les corriger.

## Interface — exigence de niveau

L'interface est un livrable de premier plan, pas un habillage. Référence : Apple et Anthropic —
sobre, dense en information sans être chargée, cohérente jusque dans les détails.

- Thème sombre, palette sémantique : chaque couleur porte un sens, aucune couleur décorative.
- Typographie distinctive — ni Inter, ni Roboto.
- Le plan de chargement est **rendu lisible** : l'utilisateur voit pourquoi 28 couches et pas 41,
  ce que coûte un contexte de 57k. C'est la valeur qui distingue EchoHub d'un lanceur de modèles.
- Animations au service de la compréhension : transitions d'état, progression réelle. Jamais
  d'effet gratuit.

## Ce qui est repris de la v1

Le `Dockerfile` et son savoir de compilation CUDA — voir `COMPATIBILITE-GPU.md`. Réintégré ligne à
ligne plutôt que copié : la v1 visait une RTX 5090 32 Go, la machine réelle est une 5080 16 Go.
`CMAKE_CUDA_ARCHITECTURES=86;120` couvre les deux GPU rencontrés, et `GGML_CUDA_FORCE_CUBLAS=ON`
contourne un segfault de nvcc 12.8 sur les kernels MMQ — que personne ne le retire pour « gagner de
la perf ».
