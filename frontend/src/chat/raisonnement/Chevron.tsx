/*
 * Chevron de dépliage, partagé par la carte d'outil et le bloc de raisonnement : les deux replis
 * doivent tourner exactement de la même façon, sinon l'œil lit deux mécanismes différents.
 */

import { motion } from 'framer-motion';
import type { ReactElement } from 'react';
import { DUR } from '../../shared/design';

export function Chevron({ ouvert }: { readonly ouvert: boolean }): ReactElement {
  return (
    <motion.svg
      viewBox="0 0 12 12"
      className="h-3 w-3 shrink-0"
      fill="none"
      aria-hidden="true"
      animate={{ rotate: ouvert ? 90 : 0 }}
      transition={{ duration: DUR.fast }}
    >
      <path d="M4.5 2.5 8 6l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </motion.svg>
  );
}
