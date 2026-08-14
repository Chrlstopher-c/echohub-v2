# Polices — binaires versionnés ici

Cinq fichiers woff2, référencés par `../fonts.css` et **présents dans le dépôt**. Ils y sont
délibérément : une police absente ne casse rien de visible au build (vite se contente d'un
avertissement) et l'application retombe silencieusement sur la pile système — le design perd sa
typographie sans que rien ne le signale. Une étape manuelle d'installation aurait ce coût à chaque
clone. 101 Ko au total, sous licence libre : le dépôt est le bon endroit.

| Fichier | Graisse | Poids |
|---|---|---|
| `IBMPlexSans-Regular.woff2` | 400 | 22 Ko |
| `IBMPlexSans-Medium.woff2` | 500 | 24 Ko |
| `IBMPlexSans-SemiBold.woff2` | 600 | 24 Ko |
| `IBMPlexMono-Regular.woff2` | 400 | 15 Ko |
| `IBMPlexMono-Medium.woff2` | 500 | 15 Ko |

Provenance : paquets `@fontsource/ibm-plex-sans@5.2.5` et `@fontsource/ibm-plex-mono@5.2.5`, jeu
latin, servis par unpkg. Ce sont les binaires officiels IBM Plex (https://github.com/IBM/plex)
redistribués tels quels. Licence SIL OFL 1.1 — l'auto-hébergement est autorisé. Pas d'italique
(refusé par DESIGN.md).

Pour les régénérer à l'identique :

```sh
b=https://unpkg.com/@fontsource/ibm-plex-sans@5.2.5/files
m=https://unpkg.com/@fontsource/ibm-plex-mono@5.2.5/files
curl -fsSL -o IBMPlexSans-Regular.woff2  $b/ibm-plex-sans-latin-400-normal.woff2
curl -fsSL -o IBMPlexSans-Medium.woff2   $b/ibm-plex-sans-latin-500-normal.woff2
curl -fsSL -o IBMPlexSans-SemiBold.woff2 $b/ibm-plex-sans-latin-600-normal.woff2
curl -fsSL -o IBMPlexMono-Regular.woff2  $m/ibm-plex-mono-latin-400-normal.woff2
curl -fsSL -o IBMPlexMono-Medium.woff2   $m/ibm-plex-mono-latin-500-normal.woff2
```
