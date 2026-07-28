import type { EditorQuickFix } from "@shared/ui";

/**
 * Apply a deterministic quick-fix to document text client-side (mirrors the
 * backend apply-fix): replace the first occurrence of `search` with `replace`
 * on `line` (1-based) if given, else the first in the whole text. Returns the
 * new text, or null if `search` no longer matches (stale fix — never corrupt).
 *
 * The replacement is treated literally (a replacer function), so `$` in the
 * replacement string carries no special meaning.
 */
export const applyQuickFix = (
  text: string,
  fix: EditorQuickFix,
): string | null => {
  const { search, replace, line } = fix;
  if (!search) return null;
  const literal = (): string => replace;

  if (line != null && line >= 1) {
    // Split keeping line terminators so re-joining preserves the document byte-for-byte.
    const parts = text.split(/(?<=\n)/);
    if (line <= parts.length) {
      const idx = line - 1;
      const target = parts[idx];
      if (target === undefined) return null;
      if (!target.includes(search)) return null;
      parts[idx] = target.replace(search, literal);
      return parts.join("");
    }
  }

  if (!text.includes(search)) return null;
  return text.replace(search, literal);
};
