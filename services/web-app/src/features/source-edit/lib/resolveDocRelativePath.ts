/**
 * Resolve a LaTeX `\input{…}` target against the including document's path,
 * both project-relative POSIX. `\input{../common/change_log}` from
 * `tz/tz.tex` → `common/change_log.tex` (LaTeX appends .tex when the target
 * has no extension). Returns null when the path escapes the project root.
 */
export const resolveDocRelativePath = (
  docPath: string,
  target: string,
): string | null => {
  const normalizedTarget = target.trim();
  if (
    normalizedTarget === "" ||
    /^[\\/]/.test(normalizedTarget) ||
    /^[A-Za-z]:/.test(normalizedTarget) ||
    /^[A-Za-z][A-Za-z0-9+.-]*:/.test(normalizedTarget) ||
    normalizedTarget.includes("\\") ||
    normalizedTarget.includes("|")
  ) {
    return null;
  }
  const withExt = /\.[A-Za-z0-9]+$/.test(normalizedTarget)
    ? normalizedTarget
    : `${normalizedTarget}.tex`;
  const base = docPath.split("/").slice(0, -1);
  for (const segment of withExt.split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") {
      if (base.length === 0) return null; // escapes the project root
      base.pop();
    } else {
      base.push(segment);
    }
  }
  return base.join("/");
};
