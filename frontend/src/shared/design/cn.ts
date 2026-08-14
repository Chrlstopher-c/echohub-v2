/* Concaténation de classes conditionnelles — évite une dépendance pour dix lignes. */
export function cn(...parts: ReadonlyArray<string | false | null | undefined>): string {
  return parts.filter((p): p is string => typeof p === 'string' && p.length > 0).join(' ');
}
