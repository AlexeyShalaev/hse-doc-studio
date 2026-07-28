/**
 * Extract zero-argument macro definitions from LaTeX source, so the visual
 * editor can render `\hseProjectName` etc. as Word-style fields with their
 * actual values. Понимает `\newcommand`/`\renewcommand`/`\providecommand`,
 * balanced braces, `%`-comments (incl. the `{%\n value}` continuation style
 * the generated `common/meta.tex` uses).
 */

const DEF_RE = /\\(?:new|renew|provide)command\*?\{\\([A-Za-z@]+)\}/g;

export const parseMacroDefinitions = (
  source: string,
): Record<string, string> => {
  const out: Record<string, string> = {};
  DEF_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = DEF_RE.exec(source))) {
    const name = match[1];
    if (!name) continue;
    let i = DEF_RE.lastIndex;
    while (i < source.length && /\s/.test(source.charAt(i))) i += 1;
    // Skip an optional argument-count spec: \newcommand{\x}[1]{…}
    if (source.charAt(i) === "[") {
      const close = source.indexOf("]", i);
      if (close === -1) continue;
      i = close + 1;
      while (i < source.length && /\s/.test(source.charAt(i))) i += 1;
    }
    if (source.charAt(i) !== "{") continue;

    let depth = 0;
    let value = "";
    let closed = false;
    for (let k = i; k < source.length; k += 1) {
      const ch = source.charAt(k);
      if (ch === "\\") {
        // Keep escapes (incl. \{ \} \%) verbatim.
        value += ch + source.charAt(k + 1);
        k += 1;
        continue;
      }
      if (ch === "%") {
        // Comment to end of line — covers the `{%` line-continuation style.
        while (k < source.length && source.charAt(k) !== "\n") k += 1;
        continue;
      }
      if (ch === "{") {
        depth += 1;
        if (depth === 1) continue;
      } else if (ch === "}") {
        depth -= 1;
        if (depth === 0) {
          closed = true;
          break;
        }
      }
      value += ch;
    }
    if (!closed) continue;
    out[name] = value.replace(/\s+/g, " ").trim();
  }
  return out;
};

/**
 * Resolve one-level aliases (`\projectname` → `\hseProjectName` → its value)
 * by substituting known macro references whose target is plain text.
 */
export const resolveMacroAliases = (
  macros: Record<string, string>,
): Record<string, string> => {
  const out = { ...macros };
  for (let pass = 0; pass < 3; pass += 1) {
    let changed = false;
    for (const [name, value] of Object.entries(out)) {
      if (!value.includes("\\")) continue;
      const next = value.replace(/\\([A-Za-z@]+)/g, (full, ref: string) => {
        const target = out[ref];
        return target !== undefined && !target.includes("\\") ? target : full;
      });
      if (next !== value) {
        out[name] = next;
        changed = true;
      }
    }
    if (!changed) break;
  }
  return out;
};
