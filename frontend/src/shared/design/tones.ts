/*
 * Vocabulaire sémantique partagé par les primitives.
 * Un « tone » est un mot du langage produit (état, ressource), jamais une couleur nommée.
 */

/** États et ressources exprimables par les primitives colorées. */
export type Tone = 'neutral' | 'accent' | 'ok' | 'caution' | 'critical' | 'vram' | 'ram' | 'kv';

/** Variable CSS de la valeur pleine de chaque tone (trait, remplissage, texte). */
export const TONE_VAR: Record<Tone, string> = {
  neutral: 'var(--text-3)',
  accent: 'var(--accent)',
  ok: 'var(--ok)',
  caution: 'var(--caution)',
  critical: 'var(--critical)',
  vram: 'var(--mem-vram)',
  ram: 'var(--mem-ram)',
  kv: 'var(--mem-kv)',
};

/** Variable CSS de la valeur douce (fonds de badges, zones de jauge). */
export const TONE_SOFT_VAR: Record<Tone, string> = {
  neutral: 'var(--surface-2)',
  accent: 'var(--accent-soft)',
  ok: 'var(--ok-soft)',
  caution: 'var(--caution-soft)',
  critical: 'var(--critical-soft)',
  vram: 'var(--mem-vram-soft)',
  ram: 'var(--mem-ram-soft)',
  kv: 'var(--mem-kv-soft)',
};
