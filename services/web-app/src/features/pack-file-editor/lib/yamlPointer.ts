import { yamlLanguage } from "@codemirror/lang-yaml";
import type { SyntaxNode } from "@lezer/common";

// JSON Pointer (RFC 6901) в строку YAML: правило из ответа «Почему?» знает файл и указатель
// (`/pack_submission/profiles/3/signing_slots/1/when`), редактор открывается на этой строке.
// Разбор берёт дерево того же парсера, что подсвечивает YAML в редакторе, поэтому лишних
// зависимостей нет. Указатель, которого в файле нет, ведёт к ближайшему найденному предку:
// лучше открыть профиль, чем промолчать.

const unescape = (segment: string): string =>
  segment.replace(/~1/g, "/").replace(/~0/g, "~");

/** Сегменты указателя: `/a/b~1c` это `["a", "b/c"]`; пустой указатель это корень. */
export const parsePointer = (pointer: string): string[] | null => {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) return null;
  return pointer.slice(1).split("/").map(unescape);
};

const child = (node: SyntaxNode, name: string): SyntaxNode | null => {
  for (let c = node.firstChild; c; c = c.nextSibling) {
    if (c.name === name) return c;
  }
  return null;
};

const keyText = (text: string, pair: SyntaxNode): string | null => {
  const key = child(pair, "Key");
  if (!key) return null;
  const raw = text.slice(key.from, key.to).trim();
  if (
    raw.length >= 2 &&
    (raw.startsWith('"') || raw.startsWith("'")) &&
    raw.endsWith(raw[0] ?? "")
  ) {
    return raw.slice(1, -1);
  }
  return raw;
};

/** Значение узла: сам блок или поток, пропуская обёртки `Item` и документа. */
const valueNode = (node: SyntaxNode): SyntaxNode | null => {
  for (let c = node.firstChild; c; c = c.nextSibling) {
    if (
      c.name === "BlockMapping" ||
      c.name === "FlowMapping" ||
      c.name === "BlockSequence" ||
      c.name === "FlowSequence"
    ) {
      return c;
    }
  }
  return null;
};

const MAPPINGS = new Set(["BlockMapping", "FlowMapping"]);
const SEQUENCES = new Set(["BlockSequence", "FlowSequence"]);

/** Элементы последовательности: `Item` блочной или потоковой. */
const items = (seq: SyntaxNode): SyntaxNode[] => {
  const out: SyntaxNode[] = [];
  for (let c = seq.firstChild; c; c = c.nextSibling) {
    if (c.name === "Item") out.push(c);
  }
  return out;
};

const pairs = (map: SyntaxNode): SyntaxNode[] => {
  const out: SyntaxNode[] = [];
  for (let c = map.firstChild; c; c = c.nextSibling) {
    if (c.name === "Pair") out.push(c);
  }
  return out;
};

/**
 * Смещение (символ) начала записи по указателю или `null`, если указатель разобрать нельзя или
 * текст пуст. Ненайденный сегмент оставляет курсор на последней найденной записи.
 */
export const pointerOffset = (text: string, pointer: string): number | null => {
  const segments = parsePointer(pointer);
  if (segments === null || text.trim() === "") return null;
  const tree = yamlLanguage.parser.parse(text);
  const doc = child(tree.topNode, "Document");
  let container: SyntaxNode | null = doc ? valueNode(doc) : null;
  let at = container?.from ?? 0;
  for (const segment of segments) {
    if (!container) break;
    let next: SyntaxNode | null = null;
    let found: SyntaxNode | null = null;
    if (MAPPINGS.has(container.name)) {
      found =
        pairs(container).find((p) => keyText(text, p) === segment) ?? null;
      next = found ? valueNode(found) : null;
    } else if (SEQUENCES.has(container.name) && /^\d+$/.test(segment)) {
      found = items(container)[Number(segment)] ?? null;
      next = found ? valueNode(found) : null;
    }
    if (!found) break;
    at = found.from;
    container = next;
  }
  return at;
};

/** Строка (с единицы) записи по указателю: то, что ждёт `reveal` редактора. */
export const pointerLine = (text: string, pointer: string): number | null => {
  const offset = pointerOffset(text, pointer);
  if (offset === null) return null;
  let line = 1;
  for (let i = 0; i < offset && i < text.length; i += 1) {
    if (text.charCodeAt(i) === 10) line += 1;
  }
  return line;
};
