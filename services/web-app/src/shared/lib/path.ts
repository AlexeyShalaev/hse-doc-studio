/**
 * Normalises a path to POSIX separators.
 *
 * The backend canonicalises check paths to forward slashes (see
 * `CheckLocation`), so API data is already POSIX. This stays as defensive
 * boundary handling for paths that also come from the URL (`?file=…`), which a
 * user could craft with backslashes, and to keep client-side path comparisons
 * OS-agnostic.
 */
export const toPosixPath = (path: string): string => path.replace(/\\/g, "/");
