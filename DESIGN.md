# Design — EchoHub v2

Direction artistique du produit. Source de vérité : `frontend/src/shared/design/`.
Ce document donne le parti pris et les règles d'arbitrage ; les valeurs exactes vivent dans
`tokens.css` et ne sont jamais dupliquées ailleurs.

## Parti pris

EchoHub manipule une ressource rare : 16 Go de VRAM, dont ~14,7 utilisables. L'interface ne cache
pas cette contrainte, elle en fait le sujet. La sensation recherchée : un instrument de mesure —
calme, précis, dense. On doit sentir que chaque chiffre affiché a été lu quelque part, pas estimé.

Référence de niveau : Apple pour la retenue, Anthropic pour la chaleur sobre. Fond presque noir,
peu de couleurs, mais chacune irremplaçable. La hiérarchie vient de la typographie et de l'espace,
jamais de la décoration.

## Principes qui tranchent les arbitrages

1. **Toute couleur est un mot du vocabulaire.** Si une couleur n'énonce pas un état, une ressource
   ou une action possible, elle n'existe pas. Le gris est la couleur par défaut de tout le reste.
2. **Les chiffres sont des mesures.** Toute valeur quantitative (Go, tok/s, couches, tokens) se
   compose en mono avec chiffres tabulaires. Un chiffre qui bouge ne saute jamais horizontalement.
3. **La progression affichée est la progression réelle.** Une barre avance parce qu'une donnée
   avance. Jamais d'animation qui simule un travail (la v1 animait 0 → 88 % en 6 s à vide).
4. **L'espace avant le trait.** La séparation se fait d'abord par l'espacement, ensuite par un
   changement de surface, en dernier recours par une bordure.
5. **Densité sans bruit.** Beaucoup d'information par écran, mais une seule taille de corps pour
   le courant (13 px), une seule famille pour l'UI, une pour les mesures.

## Refus explicites

- Progression simulée, spinners qui masquent une durée inconnue sans dire ce qui se passe.
- Couleur décorative, dégradés d'ambiance, glassmorphism, ombres colorées.
- Icônes multicolores ou illustrations : les icônes sont monochromes, trait 1,5 px.
- Cacher la contrainte matérielle (la réserve du bureau Windows est *affichée*, pas soustraite
  en silence).
- Effet d'animation sans information : pas de rebond, pas de parallaxe, pas de stagger gratuit.
- Italique dans l'UI : l'emphase passe par la graisse ou la couleur sémantique.

## Palette sémantique

Thème sombre par défaut ; le clair est défini par surcharge des mêmes tokens
(`[data-theme='light']`). Aucun composant ne référence une valeur hexadécimale : uniquement les
variables. Système parent/enfant : chaque famille a une valeur pleine (trait, texte, remplissage
plein) et une valeur `-soft` (fond de badge, zone de jauge).

| Famille | Sens | Usage |
|---|---|---|
| `--accent` (pervenche) | action possible, activité en cours | boutons primaires, focus, chargement actif |
| `--ok` (vert) | état sain, modèle prêt, mémoire confortable | badge « prêt », zone basse des jauges |
| `--caution` (ambre) | compromis, plan dégradé, erreur **récupérable** | plan replié, pression mémoire serrée |
| `--critical` (rouge) | limite atteinte, erreur **fatale** | échec définitif, mémoire critique |
| `--mem-vram` (cyan) | octets résidant en VRAM | cellules de couches GPU, jauge VRAM |
| `--mem-ram` (sable) | octets déportés en RAM — le compromis | cellules CPU ; parent : famille `--caution` |
| `--mem-kv` (orchidée) | coût du contexte (KV cache) | bloc contexte dans la jauge, slider de contexte |
| gris (`--text-*`, `--surface-*`) | tout le reste | structure, texte, états neutres |

Correspondance des états d'un modèle : inactif → gris · téléchargement/chargement → accent ·
prêt → ok · génération → accent pulsé · plan dégradé → caution · erreur fatale → critical.
Une erreur récupérable est ambre parce qu'elle *dégrade* (le planificateur replie) ; le rouge est
réservé à ce qui ne repartira pas tout seul.

## Typographie

**IBM Plex Sans** (UI) et **IBM Plex Mono** (mesures). Justification : superfamille dessinée
ensemble, donc cohérence absolue entre texte et chiffres ; caractère d'ingénierie assumé qui
colle au sujet (on pilote du silicium, pas un réseau social) ; chiffres tabulaires natifs
(`tnum`) ; licence OFL, auto-hébergeable. Ni Inter ni Roboto — et pas non plus leur physionomie :
Plex a des terminaisons franches qui restent distinctives à 13 px.

Échelle (px / interligne) : 11/1,45 · 12/1,5 · **13/1,55 (corps)** · 15/1,5 · 18/1,4 · 24/1,3 ·
32/1,2. Graisses : 400 courant, 500 libellés et boutons, 600 titres. Pas d'italique (voir refus).

Intégration : polices auto-hébergées en woff2 dans `frontend/src/shared/design/fonts/`, déclarées
dans `fonts.css`, `font-display: swap`. **Aucun CDN externe** — voir `fonts/README.md` pour la
provenance exacte des fichiers (dépôt IBM Plex, OFL 1.1).

## Échelles

- **Espacement** : grille de 4 px — 4, 8, 12, 16, 20, 24, 32, 40, 48, 64. C'est la grille
  Tailwind par défaut, volontairement : on la restreint, on ne la remplace pas.
- **Rayons** : 4 (badges, cellules), 6 (inputs, boutons), 8 (cartes), 12 (modales), plein
  (pastilles). Un composant enfant a toujours un rayon ≤ à son parent.
- **Élévation** : trois niveaux de surface (`--surface`, `--surface-2`, `--overlay`) portés par
  la teinte, plus trois ombres discrètes (`--shadow-1/2/3`). Sur fond sombre, la lumière vient de
  la surface, pas de l'ombre : l'ombre ne fait que décoller les couches flottantes.
- **Durées** : 120 ms (hover, feedback), 180 ms (transitions d'état, apparitions), 280 ms
  (modales, réagencements), linéaire pour toute progression réelle.
- **Courbes** : sorties en `cubic-bezier(0.16, 1, 0.3, 1)` (décélération franche), mouvements de
  layout en `cubic-bezier(0.65, 0, 0.35, 1)`. `prefers-reduced-motion` est respecté globalement.

## Langage visuel du plan de chargement

La pièce maîtresse. Elle répond visuellement à « pourquoi 28 couches sur 41, et que coûte 57k de
contexte ». Règles du langage :

1. **Une barre par ressource physique**, à l'échelle réelle en Go — VRAM (16 Go) et RAM
   (plafond WSL2). Jamais d'échelle normalisée : 16 Go doit *paraître* plus petit que 22 Go.
2. **La réserve est montrée.** La part du bureau Windows (~1,2 Go) ouvre la barre VRAM en zone
   hachurée neutre. La contrainte se voit, elle n'est pas soustraite en douce.
3. **Les couches sont des cellules discrètes.** 41 cellules pour 41 couches réelles (lues dans le
   GGUF, jamais déduites), largeur proportionnelle au poids réel par couche. 28 remplies en
   `--mem-vram`, 13 en `--mem-ram`. On compte des couches, on ne lit pas un pourcentage.
4. **Le contexte est un bloc qui pousse.** Le KV cache (`--mem-kv`) occupe la VRAM restante après
   les poids. Quand le slider de contexte monte, le bloc s'étend en temps réel (Framer Motion,
   animation de layout) et l'on *voit* ce que 57k confisque — et le débit prévu chuter à côté
   (41 → 19,6 tok/s sur la machine cible : l'arbitrage est le message).
5. **Chaque valeur porte sa justification** : une ligne en texte secondaire, chiffres en mono —
   « 28 couches : 28 × 436 Mo + KV 57k = 14,6 Go sur 14,7 disponibles ». Le frontend affiche la
   justification produite par le planificateur, il ne recalcule rien.
6. **Le repli se raconte en ambre.** Un plan dégradé garde la même géométrie : les cellules qui
   quittent la VRAM glissent vers la barre RAM, le badge du plan passe en `--caution` avec la
   raison. Même langage, état différent — pas d'écran d'erreur à part.

Le slider de contexte utilise des zones sémantiques : la plage où le débit mesuré s'effondre est
teintée `--caution` sous le rail. La primitive `Slider` supporte ces zones nativement.

## Contenu de `frontend/src/shared/design/`

| Fichier | Rôle |
|---|---|
| `tokens.css` | tous les tokens (palette, typo, rayons, ombres, durées) + thème clair |
| `fonts.css` / `fonts/` | déclarations `@font-face`, binaires woff2 auto-hébergés |
| `primitives.css` | styles non exprimables en Tailwind : rail de slider, scrollbar, reduced-motion |
| `tailwind-preset.ts` | expose les tokens comme thème Tailwind — l'interface publique côté classes |
| `motion.ts` | durées, courbes et variants Framer Motion partagés |
| `cn.ts` | concaténation de classes, sans dépendance |
| `Button` `Card` `Badge` `Slider` `Progress` `Tooltip` `Modal` | primitives React, variantes sémantiques |
| `index.ts` | interface publique du domaine — seul point d'import autorisé |

Les autres domaines importent uniquement `shared/design` (via `index.ts`) et le préset dans
`tailwind.config`. Importer un fichier interne du domaine est une violation de frontière.

## Limite connue

Les binaires woff2 ne sont pas dans le dépôt (pas de téléchargement dans cette passe) :
`fonts/README.md` liste les cinq fichiers exacts à déposer et leur provenance. Tant qu'ils
manquent, la pile de secours (`system-ui`) prend le relais sans casser la mise en page.
