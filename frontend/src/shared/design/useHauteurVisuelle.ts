import { useEffect } from 'react';

/*
 * Hauteur réellement visible, clavier virtuel ouvert compris.
 *
 * `100dvh` suit la barre d'URL escamotable mais IGNORE le clavier logiciel : composeur ouvert sur
 * téléphone, la zone de saisie passe sous le clavier. `visualViewport` est la seule source qui
 * décrit la fenêtre restante. Si l'API est absente, on n'écrit rien et le repli `100dvh` de
 * `.eh-hauteur-app` s'applique — ne jamais écrire une valeur devinée.
 */
const NOM_VARIABLE = '--hauteur-visuelle';

export function useHauteurVisuelle(): void {
  useEffect(() => {
    const vue = window.visualViewport;
    if (vue === null || vue === undefined) {
      return undefined;
    }
    const racine = document.documentElement;
    const appliquer = (): void => {
      try {
        racine.style.setProperty(NOM_VARIABLE, `${Math.round(vue.height)}px`);
      } catch (erreur) {
        console.warn('Hauteur visuelle non applicable', erreur);
      }
    };
    appliquer();
    vue.addEventListener('resize', appliquer);
    vue.addEventListener('scroll', appliquer);
    return (): void => {
      vue.removeEventListener('resize', appliquer);
      vue.removeEventListener('scroll', appliquer);
      racine.style.removeProperty(NOM_VARIABLE);
    };
  }, []);
}
