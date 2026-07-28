import { getDocMeta } from "@entities/document";

// Agent messages mention project documents in prose ("ВКР", «Техническое
// задание», `vkr/vkr.tex`). We turn those mentions into in-app links to
// /projects/<projectId>/documents/<docId>. References carry a custom `doc:`
// URL scheme so the markdown anchor renderer can resolve them against the
// project id available in React context (the agent never sees the project id).

export const DOC_LINK_SCHEME = "doc:";

const MIN_TOKEN_LENGTH = 2;

export type DocRefIndex = {
  regex: RegExp | null;
  lookup: (token: string) => string | undefined;
};

type MdastNode = {
  type: string;
  value?: string;
  url?: string;
  children?: MdastNode[];
};

// Nodes whose text content must not be linkified: existing links, code spans,
// and link/definition references.
const SKIP_TYPES = new Set([
  "link",
  "linkReference",
  "code",
  "inlineCode",
  "definition",
]);

const escapeRegExp = (value: string): string =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export const docHrefForId = (projectId: string, docId: string): string =>
  `/projects/${projectId}/documents/${docId}`;

export const isDocHref = (href: string | undefined): href is string =>
  typeof href === "string" && href.startsWith(DOC_LINK_SCHEME);

export const docIdFromHref = (href: string): string =>
  href.slice(DOC_LINK_SCHEME.length);

// The slice of DocumentResponse the recognizer needs — pass the API documents
// straight through so team instances resolve by their real paths/names.
export type DocRefLike = {
  id: string;
  def_id?: string | null | undefined;
  owner?: string | null | undefined;
  owner_name?: string | null | undefined;
  source_file?: string | null | undefined;
  output_file?: string | null | undefined;
  name?: Record<string, string> | null | undefined;
};

// Build a recognizer for every document that actually exists in the project.
// For each doc we accept its code (ВКР), full name, string id (vkr), and the
// .tex/.pdf paths — mapping all of them back to the same doc id.
export const buildDocRefIndex = (docs: readonly DocRefLike[]): DocRefIndex => {
  const tokenToDoc = new Map<string, string>();
  for (const doc of docs) {
    const meta = getDocMeta(doc.id, doc);
    // Team instances: bare type tokens (ВКР / vkr) are ambiguous across
    // authors — «ВКР Иванова» must not resolve to a teammate's copy. Owned
    // docs therefore only expose owner-qualified names (getDocMeta already
    // suffixes « — {owner_name}») plus their unique instance id and paths.
    const candidates = doc.owner_name
      ? [
          meta.file,
          meta.out,
          meta.name,
          `${meta.code} — ${doc.owner_name}`,
          doc.id,
        ]
      : [meta.file, meta.out, meta.name, meta.code, doc.id];
    for (const candidate of candidates) {
      const token = candidate.trim();
      if (token.length < MIN_TOKEN_LENGTH || token === "—") continue;
      if (!tokenToDoc.has(token)) tokenToDoc.set(token, doc.id);
    }
  }
  if (tokenToDoc.size === 0) {
    return { regex: null, lookup: () => undefined };
  }
  // Longest first so a file path (vkr/vkr.tex) wins over the bare id (vkr).
  const alternation = [...tokenToDoc.keys()]
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join("|");
  // \b is ASCII-only in JS, so Cyrillic codes need Unicode look-arounds to
  // avoid matching inside a longer word or path segment.
  const regex = new RegExp(
    `(?<![\\p{L}\\p{N}_/])(?:${alternation})(?![\\p{L}\\p{N}_/])`,
    "gu",
  );
  return { regex, lookup: (token) => tokenToDoc.get(token) };
};

const splitTextNode = (
  value: string,
  index: DocRefIndex,
): MdastNode[] | null => {
  if (!index.regex) return null;
  index.regex.lastIndex = 0;
  const parts: MdastNode[] = [];
  let last = 0;
  let matched = false;
  let match: RegExpExecArray | null = index.regex.exec(value);
  while (match !== null) {
    const docId = index.lookup(match[0]);
    if (docId !== undefined) {
      matched = true;
      if (match.index > last) {
        parts.push({ type: "text", value: value.slice(last, match.index) });
      }
      parts.push({
        type: "link",
        url: DOC_LINK_SCHEME + docId,
        children: [{ type: "text", value: match[0] }],
      });
      last = match.index + match[0].length;
    }
    match = index.regex.exec(value);
  }
  if (!matched) return null;
  if (last < value.length)
    parts.push({ type: "text", value: value.slice(last) });
  return parts;
};

const transform = (node: MdastNode, index: DocRefIndex): void => {
  if (!node.children) return;
  const next: MdastNode[] = [];
  for (const child of node.children) {
    if (child.type === "text" && typeof child.value === "string") {
      const split = splitTextNode(child.value, index);
      next.push(...(split ?? [child]));
      continue;
    }
    if (!SKIP_TYPES.has(child.type)) transform(child, index);
    next.push(child);
  }
  node.children = next;
};

// remark plugin: splits text nodes that mention known documents into link
// nodes carrying the `doc:` scheme. Returns a no-op when the index is empty.
export const remarkDocLinks =
  (index: DocRefIndex) => () => (tree: MdastNode) => {
    transform(tree, index);
  };
