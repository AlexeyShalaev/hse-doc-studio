/**
 * A structured, editable view of a LaTeX `thebibliography` environment for the
 * visual bibliography editor. Parsing splits it into an immutable
 * {@link BibScaffold} (the `\begin{…}{width}` wrapper, the leading gap and the
 * `\end`) and an editable {@link BibliographyDraft} (a list of `\bibitem`
 * entries with a citation key and inline-LaTeX reference text). Untouched
 * entries round-trip byte-for-byte (comments and spacing preserved);
 * {@link serializeEditableBibliography} regenerates valid LaTeX.
 *
 * This is the *lossless* model that powers the modal manager. The read-only,
 * plain-text projection used elsewhere lives in `bibliographyPreview.ts`.
 */

export type BibScaffold = {
  /** `\begin{thebibliography}{` through the width group's opening brace. */
  openBefore: string;
  /** The widest-label width argument (e.g. `99`), regenerated verbatim. */
  widthArg: string;
  /** The width group's closing brace. */
  openAfter: string;
  /** Whitespace/comments before the first `\bibitem` (kept verbatim). */
  leadGap: string;
  /** `\end{thebibliography}`. */
  close: string;
  /** The environment is well-formed (begin + width + end) and round-trips. */
  editable: boolean;
};

export type BibEntry = {
  /** Citation key used by `\cite{…}`. */
  key: string;
  /** The key at parse time; `key === keyPristine` ⇒ the marker is untouched. */
  keyPristine: string;
  /** An optional `\bibitem[label]{key}` label, kept verbatim (null = none). */
  optLabel: string | null;
  /** Original `\bibitem[…]{key}` marker source (null for new) — verbatim key. */
  markerRaw: string | null;
  /** Inline LaTeX of the reference text (rich; may contain `\textbf` etc.). */
  value: string;
  /** Original body source after the key (null for new) — for exact round-trip. */
  raw: string | null;
  /** The value at parse time; `value === pristine` ⇒ emit `raw` verbatim. */
  pristine: string;
};

export type BibliographyDraft = {
  entries: BibEntry[];
};

export type ParsedBibliography = {
  scaffold: BibScaffold;
  draft: BibliographyDraft;
};

// ---------------------------------------------------------------------------
// Low-level LaTeX scanning helpers (self-contained; mirror editableTable).
// ---------------------------------------------------------------------------

/** Commands whose first `{…}` argument is verbatim (a raw `%`/braces, not a
 *  comment): a percent-encoded URL like `\url{https://x/a%2Fb}` is common. */
const VERBATIM_ARG_COMMANDS = ["\\url", "\\nolinkurl", "\\path", "\\href"];

/** Environments whose whole body is verbatim — a `\bibitem` inside one is text,
 *  not a marker, so their interior is blanked before the marker scan. */
const VERBATIM_ENVS = new Set([
  "verbatim",
  "verbatim*",
  "Verbatim",
  "BVerbatim",
  "LVerbatim",
  "lstlisting",
  "minted",
  "alltt",
  "semiverbatim",
  "comment",
]);
const BEGIN_ENV_RE = /^\\begin\s*\{\s*([A-Za-z]+\*?)\s*\}/;

const isLetter = (character: string): boolean => /[A-Za-z]/.test(character);

/**
 * Replace `%` comment runs with spaces, preserving offsets and newlines. All
 * scanning runs on the masked copy so a `%` can't confuse brace/marker matching;
 * the serialized pieces are sliced from the ORIGINAL source, so real comments
 * inside an untouched entry survive the round-trip. Verbatim spans (`\url{…}`,
 * `\href{…}`, `\verb|…|`, an escaped `\%`) are copied intact so a raw `%` there
 * cannot swallow a brace and unbalance the marker scan.
 */
const maskComments = (source: string): string => {
  let output = "";
  let cursor = 0;
  while (cursor < source.length) {
    const character = source.charAt(cursor);
    if (character === "%") {
      // A comment: mask through the end of the line (offsets preserved).
      while (
        cursor < source.length &&
        source.charAt(cursor) !== "\n" &&
        source.charAt(cursor) !== "\r"
      ) {
        output += " ";
        cursor += 1;
      }
      continue;
    }
    if (character !== "\\") {
      output += character;
      cursor += 1;
      continue;
    }
    // `\begin{verbatim}…\end{verbatim}` (and lstlisting/minted/…) — blank the
    // whole span so a line-start `\bibitem` inside code is not seen as a marker.
    const beginEnv = BEGIN_ENV_RE.exec(source.slice(cursor));
    const envName = beginEnv?.[1];
    if (envName && VERBATIM_ENVS.has(envName)) {
      const endRe = new RegExp(
        `\\\\end\\s*\\{\\s*${envName.replace("*", "\\*")}\\s*\\}`,
      );
      const endMatch = endRe.exec(source.slice(cursor));
      const spanEnd = endMatch
        ? cursor + endMatch.index + endMatch[0].length
        : source.length;
      for (let index = cursor; index < spanEnd; index += 1) {
        const inner = source.charAt(index);
        output += inner === "\n" || inner === "\r" ? inner : " ";
      }
      cursor = spanEnd;
      continue;
    }
    // `\url{…}` / `\href{…}` / … — copy the command + one verbatim `{…}` arg.
    const command = VERBATIM_ARG_COMMANDS.find(
      (name) =>
        source.startsWith(name, cursor) &&
        !isLetter(source.charAt(cursor + name.length)),
    );
    if (command) {
      output += command;
      cursor += command.length;
      while (cursor < source.length && /\s/.test(source.charAt(cursor))) {
        output += source.charAt(cursor);
        cursor += 1;
      }
      if (source.charAt(cursor) === "{") {
        let depth = 0;
        do {
          const inner = source.charAt(cursor);
          output += inner;
          if (inner === "{") depth += 1;
          else if (inner === "}") depth -= 1;
          cursor += 1;
        } while (cursor < source.length && depth > 0);
      }
      continue;
    }
    // `\verb<delim>…<delim>` (and `\verb*`) — copy verbatim to the closing delim.
    if (source.startsWith("\\verb", cursor)) {
      let probe = cursor + "\\verb".length;
      if (source.charAt(probe) === "*") probe += 1;
      const delimiter = source.charAt(probe);
      if (delimiter && delimiter !== " " && !isLetter(delimiter)) {
        output += source.slice(cursor, probe + 1);
        cursor = probe + 1;
        while (
          cursor < source.length &&
          source.charAt(cursor) !== delimiter &&
          source.charAt(cursor) !== "\n"
        ) {
          output += source.charAt(cursor);
          cursor += 1;
        }
        if (cursor < source.length) {
          output += source.charAt(cursor);
          cursor += 1;
        }
        continue;
      }
    }
    // An ordinary control sequence / escaped char — copy `\` + the next char so
    // an escaped `\%` never starts a comment.
    output += character + (source.charAt(cursor + 1) || "");
    cursor += 2;
  }
  return output;
};

const skipWhitespace = (source: string, from: number): number => {
  let cursor = from;
  while (cursor < source.length && /\s/.test(source.charAt(cursor)))
    cursor += 1;
  return cursor;
};

type Group = { content: string; end: number };

const readGroup = (
  source: string,
  from: number,
  opening = "{",
  closing = "}",
): Group | undefined => {
  if (source.charAt(from) !== opening) return undefined;
  let depth = 1;
  for (let cursor = from + 1; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "\\") {
      cursor += 1;
      continue;
    }
    if (character === opening) depth += 1;
    else if (character === closing) {
      depth -= 1;
      if (depth === 0) {
        return { content: source.slice(from + 1, cursor), end: cursor + 1 };
      }
    }
  }
  return undefined;
};

const BEGIN_RE = /\\begin\s*\{\s*thebibliography\s*\}/;
const END_RE = /\\end\s*\{\s*thebibliography\s*\}/;
const BIBITEM = "\\bibitem";

/** Collapse a body run to a single logical line for editing (raw keeps breaks). */
const normalizeValue = (body: string): string =>
  body.replace(/\s+/g, " ").trim();

/** Strip characters that would break the `{key}` group or a `\cite` key. */
export const sanitizeKey = (key: string): string =>
  key.replace(/[{}[\]\\%#~^$,\s]/g, "");

const makeMarker = (key: string, optLabel: string | null): string =>
  optLabel !== null
    ? `${BIBITEM}[${optLabel}]{${sanitizeKey(key)}}`
    : `${BIBITEM}{${sanitizeKey(key)}}`;

/**
 * Body-relative offsets of every REAL `\bibitem` marker: a `\bibitem` control
 * word that is the FIRST non-whitespace on its line. This skips a literal
 * `\bibitem` quoted mid-prose (e.g. a thesis discussing LaTeX). Detection is
 * deliberately NOT brace-depth based — a verbatim brace (`\verb|{|`) or a
 * comment-masked closing brace would poison a depth counter and silently merge
 * the next entry; every real bibliography puts each `\bibitem` at line start.
 */
const findBibitemMarkers = (maskedBody: string): number[] => {
  const starts: number[] = [];
  let atLineStart = true;
  for (let cursor = 0; cursor < maskedBody.length; cursor += 1) {
    const character = maskedBody.charAt(cursor);
    if (character === "\\") {
      if (
        atLineStart &&
        maskedBody.startsWith(BIBITEM, cursor) &&
        !/[A-Za-z]/.test(maskedBody.charAt(cursor + BIBITEM.length))
      ) {
        starts.push(cursor);
      }
      cursor += 1; // skip the escaped next character
      atLineStart = false;
      continue;
    }
    if (character === "\n") atLineStart = true;
    else if (!/\s/.test(character)) atLineStart = false;
  }
  return starts;
};

// ---------------------------------------------------------------------------
// Parsing.
// ---------------------------------------------------------------------------

/** Parse the first `thebibliography` environment, or null when there is none. */
export const parseEditableBibliography = (
  source: string | undefined,
): ParsedBibliography | null => {
  if (!source) return null;
  const masked = maskComments(source);

  const begin = BEGIN_RE.exec(masked);
  if (!begin) return null;
  let cursor = begin.index + begin[0].length;

  // The mandatory {widest-label} width group.
  cursor = skipWhitespace(masked, cursor);
  const widthOpen = cursor;
  const widthGroup = readGroup(masked, cursor);
  if (!widthGroup) return null;
  const bodyStart = widthGroup.end;
  const openBefore = source.slice(begin.index, widthOpen + 1);
  const widthArg = source.slice(widthOpen + 1, widthGroup.end - 1);
  const openAfter = source.slice(widthGroup.end - 1, bodyStart); // just the "}"

  const end = END_RE.exec(masked.slice(bodyStart));
  if (!end) return null;
  const bodyEnd = bodyStart + end.index;
  const close = source.slice(bodyEnd, bodyEnd + end[0].length);
  const body = source.slice(bodyStart, bodyEnd); // original (comments kept)
  const maskedBody = masked.slice(bodyStart, bodyEnd); // for scanning

  const starts = findBibitemMarkers(maskedBody);
  type Marker = {
    start: number;
    keyEnd: number;
    key: string;
    optLabel: string | null;
    markerRaw: string;
  };
  const markers: Marker[] = [];
  // Marker offsets from findBibitemMarkers are RELATIVE to the body, so slice
  // the verbatim pieces from `body` (not the absolute `source`).
  for (const start of starts) {
    let after = skipWhitespace(maskedBody, start + BIBITEM.length);
    let optLabel: string | null = null;
    if (maskedBody.charAt(after) === "[") {
      const label = readGroup(maskedBody, after, "[", "]");
      if (label) {
        optLabel = body.slice(after + 1, label.end - 1);
        after = skipWhitespace(maskedBody, label.end);
      }
    }
    const keyGroup = readGroup(maskedBody, after);
    if (!keyGroup) continue;
    markers.push({
      start,
      keyEnd: keyGroup.end,
      key: body.slice(after + 1, keyGroup.end - 1).trim(),
      optLabel,
      markerRaw: body.slice(start, keyGroup.end),
    });
  }

  const leadGap = body.slice(
    0,
    markers.length > 0 ? (markers[0]?.start ?? 0) : body.length,
  );

  const entries: BibEntry[] = markers.map((marker, index) => {
    const next = markers[index + 1];
    const stop = next ? next.start : body.length;
    const rawBody = body.slice(marker.keyEnd, stop);
    const value = normalizeValue(maskedBody.slice(marker.keyEnd, stop));
    return {
      key: marker.key,
      keyPristine: marker.key,
      optLabel: marker.optLabel,
      markerRaw: marker.markerRaw,
      value,
      raw: rawBody,
      pristine: value,
    };
  });

  return {
    scaffold: {
      openBefore,
      widthArg,
      openAfter,
      leadGap,
      close,
      editable: true,
    },
    draft: { entries },
  };
};

// ---------------------------------------------------------------------------
// Serialization.
// ---------------------------------------------------------------------------

const entrySource = (entry: BibEntry): string => {
  // Untouched key → emit the verbatim marker; an edited key regenerates it
  // (sanitized so a stray `}` / `\` / `%` can never unbalance the environment).
  const marker =
    entry.markerRaw !== null && entry.key === entry.keyPristine
      ? entry.markerRaw
      : makeMarker(entry.key, entry.optLabel);
  // Untouched body → emit the original slice verbatim (spacing/comments/markup
  // and its own trailing gap). An edited/new body carries an explicit gap so it
  // never runs into the next marker.
  const body =
    entry.raw !== null && entry.value === entry.pristine
      ? entry.raw
      : `\n${entry.value}\n\n`;
  return `${marker}${body}`;
};

export const serializeEditableBibliography = (
  scaffold: BibScaffold,
  draft: BibliographyDraft,
): string => {
  const head = `${scaffold.openBefore}${scaffold.widthArg}${scaffold.openAfter}`;
  const body = `${scaffold.leadGap}${draft.entries.map(entrySource).join("")}`;
  return `${head}${body}${scaffold.close}`;
};

// ---------------------------------------------------------------------------
// Pure editing operations on the draft.
// ---------------------------------------------------------------------------

const emptyEntry = (): BibEntry => ({
  key: "",
  keyPristine: "",
  optLabel: null,
  markerRaw: null,
  value: "",
  raw: null,
  pristine: "",
});

export const setEntryKey = (
  draft: BibliographyDraft,
  index: number,
  key: string,
): BibliographyDraft => ({
  entries: draft.entries.map((entry, i) =>
    i === index ? { ...entry, key } : entry,
  ),
});

export const setEntryValue = (
  draft: BibliographyDraft,
  index: number,
  value: string,
): BibliographyDraft => ({
  entries: draft.entries.map((entry, i) =>
    i === index ? { ...entry, value } : entry,
  ),
});

export const addEntry = (
  draft: BibliographyDraft,
  atIndex?: number,
): BibliographyDraft => {
  const index = atIndex ?? draft.entries.length;
  const entries = [...draft.entries];
  entries.splice(Math.min(Math.max(index, 0), entries.length), 0, emptyEntry());
  return { entries };
};

export const removeEntry = (
  draft: BibliographyDraft,
  index: number,
): BibliographyDraft => ({
  entries: draft.entries.filter((_, i) => i !== index),
});

export const moveEntry = (
  draft: BibliographyDraft,
  from: number,
  to: number,
): BibliographyDraft => {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= draft.entries.length ||
    to >= draft.entries.length
  ) {
    return draft;
  }
  const entries = [...draft.entries];
  const [item] = entries.splice(from, 1);
  if (item !== undefined) entries.splice(to, 0, item);
  return { entries };
};

/** True when any entry has an empty/whitespace-only key (blocks a valid save). */
export const hasEmptyKey = (draft: BibliographyDraft): boolean =>
  draft.entries.some((entry) => sanitizeKey(entry.key).length === 0);
