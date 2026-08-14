import type { Config } from 'tailwindcss';

/*
 * Préset Tailwind du design system — projette les tokens CSS en classes.
 * Les valeurs vivent dans tokens.css ; ici on ne fait que les nommer.
 * Usage dans tailwind.config : presets: [designPreset].
 */
export const designPreset: Config = {
  content: [],
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      bg: 'var(--bg)',
      surface: 'var(--surface)',
      'surface-2': 'var(--surface-2)',
      overlay: 'var(--overlay)',
      border: 'var(--border)',
      'border-strong': 'var(--border-strong)',
      text: 'var(--text)',
      'text-2': 'var(--text-2)',
      'text-3': 'var(--text-3)',
      accent: 'var(--accent)',
      'accent-hover': 'var(--accent-hover)',
      'accent-soft': 'var(--accent-soft)',
      'on-accent': 'var(--on-accent)',
      ring: 'var(--ring)',
      ok: 'var(--ok)',
      'ok-soft': 'var(--ok-soft)',
      caution: 'var(--caution)',
      'caution-soft': 'var(--caution-soft)',
      critical: 'var(--critical)',
      'critical-soft': 'var(--critical-soft)',
      'mem-vram': 'var(--mem-vram)',
      'mem-vram-soft': 'var(--mem-vram-soft)',
      'mem-ram': 'var(--mem-ram)',
      'mem-ram-soft': 'var(--mem-ram-soft)',
      'mem-kv': 'var(--mem-kv)',
      'mem-kv-soft': 'var(--mem-kv-soft)',
      scrim: 'var(--scrim)',
    },
    fontFamily: {
      ui: 'var(--font-ui)',
      mono: 'var(--font-mono)',
    },
    fontSize: {
      // Échelle unique, alignée sur tokens.css — pas d'autres tailles dans l'app.
      '2xs': ['var(--text-2xs)', { lineHeight: '1.45' }],
      xs: ['var(--text-xs)', { lineHeight: '1.5' }],
      sm: ['var(--text-sm)', { lineHeight: '1.55' }],
      md: ['var(--text-md)', { lineHeight: '1.5' }],
      lg: ['var(--text-lg)', { lineHeight: '1.4' }],
      xl: ['var(--text-xl)', { lineHeight: '1.3' }],
      '2xl': ['var(--text-2xl)', { lineHeight: '1.2' }],
    },
    borderRadius: {
      none: '0',
      xs: 'var(--radius-xs)',
      sm: 'var(--radius-sm)',
      md: 'var(--radius-md)',
      lg: 'var(--radius-lg)',
      full: '9999px',
    },
    boxShadow: {
      none: 'none',
      1: 'var(--shadow-1)',
      2: 'var(--shadow-2)',
      3: 'var(--shadow-3)',
    },
    extend: {
      transitionDuration: {
        fast: 'var(--dur-fast)',
        base: 'var(--dur-base)',
        slow: 'var(--dur-slow)',
      },
      transitionTimingFunction: {
        out: 'var(--ease-out)',
        'in-out': 'var(--ease-in-out)',
      },
      keyframes: {
        // Pouls des états actifs (génération en cours) — le seul mouvement en boucle autorisé.
        'eh-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
      },
      animation: {
        'eh-pulse': 'eh-pulse 1.6s var(--ease-in-out) infinite',
      },
    },
  },
};
