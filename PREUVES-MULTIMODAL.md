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
