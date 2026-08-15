import { useEffect, useState } from 'react';

/*
 * Seuil unique de l'application : 1024 px (`lg` de Tailwind). En dessous, les colonnes latérales
 * du chat deviennent des tiroirs ; au-dessus elles reprennent leur place en flux.
 *
 * Le seuil est lu en JS et non seulement en CSS parce que la bascule change la STRUCTURE du DOM
 * (portal + voile ou passe-plat), pas seulement l'apparence — une media query ne peut pas décider ça.
 */
const REQUETE_GRAND_ECRAN = '(min-width: 1024px)';

export function useEstGrandEcran(): boolean {
  const [estGrand, setEstGrand] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return true;
    }
    return window.matchMedia(REQUETE_GRAND_ECRAN).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const liste = window.matchMedia(REQUETE_GRAND_ECRAN);
    const surChangement = (evenement: MediaQueryListEvent): void => setEstGrand(evenement.matches);
    setEstGrand(liste.matches);
    liste.addEventListener('change', surChangement);
    return (): void => liste.removeEventListener('change', surChangement);
  }, []);

  return estGrand;
}
