# STATE — EchoHub v2

*Dernière mise à jour : 2026-08-15*

## Résumé de l'état actuel

L'application tourne, en Docker, sur RTX 5080 / WSL2. On charge un modèle GGUF depuis un plan
calculé, on discute avec, le modèle appelle réellement des outils (recherche web via SearXNG
local), et l'interface montre son raisonnement, ses appels d'outils et l'occupation du contexte.

Six domaines backend montés, **53 opérations HTTP**, **196 tests Python verts**, typage TypeScript
strict sans `any`. Accès local et LAN (`http://10.0.0.6:37920`).

Le socle est solide ; ce qui manque est fonctionnel, pas structurel. Le prochain gros chantier est
le bac à sable d'exécution de code et les artefacts (voir TODO.md, en tête).

## Ce qui a été fait — session du 2026-08-14 au 2026-08-15

**Reconstruction complète.** La v1 (`../echohub-master`) a été abandonnée après plusieurs heures
de correctifs : ses constantes étaient calibrées pour une RTX 3060 sur Linux natif et chacune se
retournait contre cette machine. La v2 a été bâtie par un workflow de 15 agents, puis assemblée et
corrigée à la main.

**Livré et vérifié en réel :**

- Chargement piloté par un planificateur : plan affiché avec ses justifications avant application,
  dégradation strictement plus conservatrice après échec.
- Chat complet — Markdown natif, raisonnement repliable, actions au survol (copier, éditer,
  rejouer en sous-branche), réglages par conversation, branches de messages.
- Harnais d'outils : socle de prompt système, recherche web SearXNG, appels affichés en direct
  avec entrée et sortie distinctes.
- Panneau d'occupation du contexte, mesuré par le tokenizer du modèle chargé.
- Écran Modèles : recherche Hub avec filtres de capacités, registre local, transferts, favoris,
  inventaire du disque, menu contextuel.
- Clic droit sur conversations et modèles, renommage en place.

**Mesures de référence sur cette machine :**

| Modèle | Contexte | Débit |
|---|---|---|
| Qwen2.5-0.5B Q4_K_M | 32 768 | 113–120 tok/s |
| Qwen3.6-27B PHILADELPHIA Q3_K_M | 32 768 | ~72 tok/s |
| Qwen3.6-35B-A3B IQ4_XS (29/41 couches GPU) | 32 768 | 41 tok/s |
| idem | 57 344 | 19,6 tok/s |

## Décisions prises

| Décision | Raison | Date |
|---|---|---|
| Un seul appel moteur par tour, outils déclarés dedans | Deux appels aux prompts différents invalident le cache de prompt de llama.cpp : deux évaluations complètes avant le premier token, des dizaines de secondes sur un 27B partiellement en RAM | 2026-08-15 |
| Socle de prompt système avant celui de la conversation | Sans outils déclarés, les modèles annoncent savoir chercher sur le web puis fabriquent des résultats | 2026-08-14 |
| Accepter deux dialectes d'appel d'outil | Les gabarits GGUF émettent soit du JSON dans `<tool_call>`, soit du balisage `<function=…>`. Aucun n'est devinable à l'avance | 2026-08-15 |
| Résultats d'outils en balises textuelles, pas en événements de flux | Un événement disparaît au rechargement ; une balise persiste avec le message et garde la réponse vérifiable | 2026-08-15 |
| Marge de libération VRAM à 768 Mo | Mesurée : 305 puis 384 Mo de résidu (contexte CUDA du processus, jamais rendu tant qu'il vit). À 256 Mo, aucun second chargement n'était possible | 2026-08-15 |
| Favoris en base, pas dans le navigateur | La bibliothèque est la même depuis le poste et depuis le téléphone | 2026-08-15 |
| Inventaire du disque distinct du registre | Le registre n'expose que le chargeable ; les dossiers refusés étaient invisibles ET indestructibles — 15,7 Go inaccessibles | 2026-08-15 |
| Marqueur de fin d'étape posé après coup | Au début d'un tour, rien ne dit s'il produira un appel ou la réponse : ouvrir une balise « au cas où » replierait la réponse dans le cas le plus fréquent | 2026-08-15 |

## Contexte non-évident

**La v1 était calibrée pour une autre machine.** RTX 3060, Linux natif. Trois de ses constantes se
sont retournées contre celle-ci : nombre de couches codé en dur, heuristique de 150 Mo par couche
(436 Mo mesurés), et mémoire unifiée CUDA — inutilisable sous WSL2, qui ne supporte pas
l'oversubscription et laisse les poids en RAM hôte avec la VRAM figée à 2 Go. C'est la première
hypothèse à tester devant tout symptôme mémoire inexpliqué.

**`GGML_CUDA_FORCE_CUBLAS=ON` n'est pas cosmétique.** Sans lui, nvcc de CUDA 12.8 segfaute en
compilant les kernels MMQ de ggml pour `compute_120a`. Bug du compilateur, pas du code. Le retirer
« pour gagner de la perf » casse le build. Détail dans COMPATIBILITE-GPU.md.

**La syntaxe GPU de Docker est inversée entre plateformes.** `deploy.resources.reservations`
sur Windows/WSL2, CDI `nvidia.com/gpu=all` sur Linux natif. Les deux formes sont dans
docker-compose.yml, une seule active.

**Les identifiants contiennent des `/`.** Un identifiant de registre ou de transfert vaut
`<depot>::<fichier>` et le dépôt porte un `/`. Le navigateur l'encode en `%2F`, le serveur le
décode avant le routage : toute route les recevant a besoin de `:path`, avec les routes suffixées
déclarées **avant** la route nue, `:path` étant glouton. Ce défaut a frappé deux fois — registre,
puis transferts — parce que la première correction n'avait pas été généralisée.

**Pydantic ne sérialise pas les `@property`.** Une valeur calculée côté backend et exposée par une
propriété simple n'atteint jamais le navigateur. C'est ce qui bloquait tous les MoE : la largeur
FFN active existait et était juste, mais invisible. `computed_field` est obligatoire dès qu'une
dérivée doit voyager.

**Aucune authentification.** Le port 37920 est ouvert sur le LAN : n'importe qui sur le réseau peut
charger, éjecter et interroger un modèle. Acceptable en usage domestique, à traiter avant toute
exposition.

**Sécurité, à ne pas perdre de vue.** Un jeton GitHub `ghp_…` a été collé en clair dans une
conversation le 2026-08-14 : il doit être considéré comme compromis et révoqué
(https://github.com/settings/tokens). L'authentification se fait désormais par `gh auth login --web`,
et le jeton OAuth qui en résulte est dans le gestionnaire d'identifiants Windows de cette machine —
qui n'est pas celle de Chris. `gh auth logout` avant de la rendre.

## Prochaines étapes

Ordonnées dans TODO.md. En tête : **bac à sable d'exécution de code et artefacts** — le script de
workflow est prêt et les faits d'isolation déjà mesurés.

## Points en suspens

- **Le MoE n'a jamais été chargé en conditions réelles.** Il est planifiable depuis le 2026-08-15,
  mais aucune mesure. C'est le test qui dira si les 6 Go de VRAM inutilisés sont récupérés.
- **Qwen3-Coder-30B en plusieurs parts** : le correctif est écrit, jamais éprouvé sur un vrai
  téléchargement découpé.
- **ccremote** (`../ccremote`, branche `local-models`) : adapté aux modèles locaux via API
  compatible OpenAI, pile Docker en place, mais l'orchestrateur exige des identifiants Claude.
  Trois voies avaient été proposées, aucune tranchée.

## Historique

**2026-08-14 — Journée v1.** Lancement sous Windows, installation de Docker Desktop et WSL2,
quatre correctifs pour démarrer (import absent du dépôt amont, `start.ps1` tué par stderr sous
PowerShell 5.1, syntaxe GPU CDI rejetée, `mcp_server.py` inexistant). Puis diagnostic du MoE :
plusieurs heures perdues à supposer un manque de VRAM avant de tester un modèle connu-bon de
490 Mo, qui a généré immédiatement et disculpé toute la chaîne. Décision de reconstruire.
