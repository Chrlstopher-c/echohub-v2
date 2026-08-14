# Architecture — EchoHub v2

## Périmètre du MVP

**Dans le MVP :**

| Domaine | Ce qu'il fait |
|---|---|
| `system` | Détecte matériel et plateforme : GPU, VRAM, RAM, WSL2 ou Linux natif, pilote |
| `engines` | Installe et gère llama.cpp et vLLM, leurs versions et venvs |
| `models` | Cherche sur Hugging Face, télécharge, lit les métadonnées GGUF, tient le registre local |
| `inference` | **Planificateur de chargement** + pilotage des moteurs + génération |
| `chat` | Conversations, streaming des réponses, persistance |

**Hors MVP, volontairement** — à ne pas commencer, à ne pas préparer « au cas où » : RAG et
ChromaDB, skills MCP, connecteurs (Discord), fine-tuning, recherche web.

**Exception unique** : le service SearXNG figure dans `docker-compose.yml` sous un profil Docker
**inactif par défaut**. Il ne démarre pas, ne consomme rien, et évite d'avoir à retoucher
l'infrastructure quand la recherche web arrivera.

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
  inference/   planificateur, adaptateurs de moteurs, génération
  chat/        conversations et persistance
  core/        config, logging, erreurs, base de données
frontend/src/
  models/      écrans de découverte et gestion des modèles
  chat/        écran de conversation
  system/      matériel, moteurs, réglages
  shared/      design system, composants, client API
```

Chaque domaine expose une interface publique. Un domaine n'importe jamais les internes d'un autre.

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

Le `Dockerfile` et son savoir de compilation CUDA — voir `COMPATIBILITE-GPU.md`. À **réintégrer
en comprenant chaque ligne**, pas à copier tel quel : la v1 vise une RTX 5090 32 Go, la machine
réelle est une 5080 16 Go.
