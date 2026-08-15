# Preuves — mesure du coût multimodal et garde-fou VRAM

Mission de mesure. Trois preuves attendues, consignées ici dès obtention (pas de synthèse
différée). Machine : Arch Linux natif, RTX 3060 12 Go, `llama-cpp-python` 0.3.34. Image
conteneur reconstruite depuis ce worktree (commit `1c2c605`) — vérifié par `grep` du symbole
`_detacher_vision_si_vram_insuffisante` DANS l'image après build, avant tout test, pour ne
pas répéter l'échec de la tentative précédente (conteneur exécutant du code périmé).

Modèle de vision utilisé : `Qwen3-VL-8B-Instruct-Q4_K_M.gguf` + `mmproj-Qwen3-VL-8B-Instruct-F16.gguf`
(`/mnt/models/lmstudio-community/Qwen3-VL-8B-Instruct-GGUF`) — c'est le modèle de vision le
plus léger disponible sur la machine avec un projecteur (`mmproj*.gguf`) présent à ses côtés,
et c'est celui sur lequel le diagnostic du plantage natif (5,9 Gio) a été mesuré. Ce dossier
n'est pas sous le montage `:ro` par défaut du conteneur (`/mnt/models/echohub`) : un second
montage `:ro` a été ajouté au lancement du conteneur (`docker run` manuel, pas de modification
de `docker-compose.yml`), sans écriture sur aucun fichier de modèle.

## Preuve 1 — le garde-fou est reconfirmé au contexte de production

**Obtenue.**

Chargement de Qwen3-VL-8B-Instruct + mmproj via `POST /inference/planifier` puis
`POST /inference/charger`, avec `preferences.contexte = 262144` (contexte par défaut du
projet, passé directement dans la requête `demande` de planification — pas via le curseur de
l'interface).

Plan retenu par le planificateur (VRAM libre avant chargement : 11 192 Mo) : 8 couches sur 36
en GPU, cache KV f16 sur 262144 tokens (8,59 Gio), flash attention activée. Chargement réussi
en 20,8 s, VRAM utilisée après chargement : 11 488 Mo — VRAM libre restante : **799 Mo**, bien
sous la marge de 6144 Mo mesurée nécessaire à l'encodeur visuel.

Entrée de journal produite par le garde-fou (`session_journal 595b71c145d7`), automatiquement,
juste après le chargement :

```
[avertissement] Projecteur de vision détaché : VRAM libre (799 Mo) sous la marge mesurée pour
l'encodeur visuel (6144 Mo). Une initialisation aurait planté le processus (SIGABRT natif, non
rattrapable) au premier comptage ou à la première image envoyée. Le modèle reste chargé, le
repli sans vision (2.4) s'applique désormais aux deux : mesure et génération.
```

Requête réelle de comptage envoyée ensuite (`POST /inference/contexte`, message utilisateur
avec une image jointe) :

```
$ curl -X POST http://localhost:37921/inference/contexte -d '{"messages":[{"role":"user",
  "content":[{"type":"text","text":"Décris cette image."},
             {"type":"image_chemin","chemin":"/data/preuves-images/petite.png",
              "type_mime":"image/png"}]}]}'

HTTP 200
{"mesurable":false,
 "raison":"Aucun projecteur de vision chargé avec ce modèle : le coût d'une image n'est pas mesurable.",
 "moteur":"llama.cpp","modele":"lmstudio-community/Qwen3-VL-8B-Instruct-GGUF::Qwen3-VL-8B-Instruct-Q4_K_M.gguf",
 "contexte_plan":262144, ...}
```

Conteneur vérifié vivant après l'appel : `docker ps` → `Up About a minute` (aucun redémarrage,
aucun SIGABRT). Au contexte de production, la requête réelle de comptage ne plante plus le
conteneur : la vision est détachée proprement au chargement et la mesure répond une absence
nommée, jamais un crash.

## Preuve 2 — les trois chiffres de la mesure, contexte réduit

**Obtenue.**

Rechargement de Qwen3-VL-8B-Instruct + mmproj avec `preferences.contexte = 4096` et
`preferences.couches_gpu = 16` (contexte réduit passé directement à la requête de
planification, pas via le curseur de l'interface) : budget retenu 3,16 Gio sur 11,62 Gio
libres, soit ~7,9 Gio de marge restante — largement au-dessus des 6 Gio requis. VRAM
effectivement utilisée après chargement : 4 102 684 672 - 1 263 140 864 ≈ 2,64 Gio. Journal de
chargement : aucun avertissement de détachement (« Projecteur de vision chargé »
uniquement) — la vision reste attachée, contrairement à la preuve 1.

Deux images de test générées (motif pseudo-aléatoire par blocs de 8×8, pour éviter qu'un
encodeur optimise un aplat de couleur uniforme) : `petite.png` (128×128) et `grande.png`
(896×896).

**Chiffre 1 et 2 — la même image mesurée deux fois rend exactement le même nombre :**

```
$ curl -X POST /inference/contexte  (petite.png, 1er appel)  → postes.images.tokens = 18
$ curl -X POST /inference/contexte  (petite.png, 2e appel)   → postes.images.tokens = 18
```

**Chiffre 3 — une image sensiblement plus grande rend un nombre différent et supérieur :**

```
$ curl -X POST /inference/contexte  (grande.png, 896×896)    → postes.images.tokens = 786
```

18 → 18 → 786 : identique sur la répétition, strictement supérieur sur l'image agrandie.

**Sans projecteur chargé, mesure impossible — jamais zéro :**

Modèle `unsloth/Qwen3-VL-2B-Instruct-GGUF` (Q4_K_M) chargé à la place — son dossier ne contient
AUCUN fichier `mmproj*.gguf` (vérifié : 14 quantifications présentes, 0 projecteur), donc
`chat_handler` n'existe jamais pour cette instance, sans intervention du garde-fou :

```
$ curl -X POST /inference/contexte  (petite.png, sans projecteur)
{"mesurable":false,
 "raison":"Aucun projecteur de vision chargé avec ce modèle : le coût d'une image n'est pas mesurable.",
 ...}
```

Aucun champ `tokens_mesures` chiffré : l'absence de mesure est nommée, jamais rendue par un 0.

**Les trois valeurs mesurées : 18, 18, 786.**

## Preuve 3 — le repli sans tour de vision, via l'interface réelle

**Obtenue.**

Modèle chargé : `unsloth/Qwen3-VL-2B-Instruct-GGUF::Qwen3-VL-2B-Instruct-Q4_K_M.gguf` — aucun
`mmproj*.gguf` dans son dossier (14 quantifications présentes, 0 projecteur), donc jamais de
`chat_handler`. Test mené dans le navigateur réel (Playwright, Chromium headless), pas en
appel HTTP direct : composeur du Chat, image `petite.png` déposée via l'`input[type=file]`
caché (`data-testid="entree-fichier"`), message tapé, bouton **Envoyer** cliqué.

Premier essai (« Que vois-tu sur cette image ? ») : envoi non bloqué, génération de 286 tokens
à 80,5 tok/s, mais le modèle n'a produit que du raisonnement (tentatives d'appel de l'outil
`presenter_fichier`, bornées à 3 tours) sans texte de réponse final — comportement du modèle
documenté par ailleurs dans `TODO.md` (ré-émission d'appel d'outil), pas un blocage de
l'application. Extrait de son raisonnement, à l'Étape 1, dans ses propres mots :

> « L'image que vous avez jointe est une image de 128×128 pixels, d'une taille de 1 Ko. J'ai
> besoin de voir l'image pour répondre à votre question. Pour cela, je vais utiliser le tool
> `presenter_fichier` afin de montrer la capture d'écran de l'image. »

Second essai, nouvelle conversation, même modèle, même image, prompt reformulé pour éviter la
boucle d'outils (« Sans appeler aucun outil, dis-moi en une phrase ce que tu sais de cette
image d'après sa description. ») : envoi non bloqué, génération complète de 144 tokens à
89,1 tok/s. **Réponse du modèle, intégrale, telle qu'affichée dans le fil :**

> « Je ne peux pas analyser l'image car elle n'est pas accessible ici. Pour obtenir une
> description de l'image, je devrais avoir la capacité d'observer ou d'intégrer les données
> visuelles. L'image que vous avez jointe est décrite comme étant une image de 128x128 pixels
> et de taille 1 Ko, mais sans pouvoir voir ou interpréter cette image, je ne peux pas donner
> une description précise de sa nature, de ses couleurs, de son contenu ou de tout autre
> détail visuel. Si vous avez des informations supplémentaires sur l'image que vous voudriez
> comprendre, veuillez me les fournir. »

C'est le modèle qui dit, avec ses mots, qu'il ne peut pas voir l'image — jamais l'application.

**Assertion Playwright** (`browser_evaluate` sur `document.body.innerText`, page entière après
génération) : recherche insensible à la casse de « ne prend pas en charge », « non supporté(e) »,
« unsupported », « not supported ». Résultat : `formules_trouvees: []`, sur 2408 caractères de
DOM. Aucune erreur console ni erreur de page (`browser_get_console_errors` → `total: 0`).
Capture d'écran : `logs/screenshots/preuve3_repli_sans_vision.png`.
