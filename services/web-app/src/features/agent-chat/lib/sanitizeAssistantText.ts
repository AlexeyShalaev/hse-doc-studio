// Local models (e.g. qwen2.5) often "narrate" a tool call by printing its raw
// JSON in the assistant text — as a <tool_call> block, a ```json fence, or a
// bare object — in addition to the real call (which renders as its own card).
// That JSON is noise for the reader, so we strip it from the DISPLAYED text
// only. Tool execution and the tool-call cards are unaffected.

const TOOL_CALL_TAG_RE = /<tool_call>[\s\S]*?<\/tool_call>/g;
const FENCE_RE = /```[^\n]*\n([\s\S]*?)```/g;
const STRAY_TAG_RE = /<\/?tool_call>/g;

const isToolCallObject = (raw: string): boolean => {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{")) return false;
  try {
    const parsed: unknown = JSON.parse(trimmed);
    return (
      typeof parsed === "object" &&
      parsed !== null &&
      "name" in parsed &&
      "arguments" in parsed &&
      typeof (parsed as { name: unknown }).name === "string"
    );
  } catch {
    return false;
  }
};

// Index of the `}` that closes the `{` at `start`, respecting strings; -1 if none.
const matchBrace = (text: string, start: number): number => {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
};

const stripBareToolCalls = (text: string): string => {
  let result = "";
  let i = 0;
  while (i < text.length) {
    if (text.charAt(i) === "{") {
      const end = matchBrace(text, i);
      if (end !== -1 && isToolCallObject(text.slice(i, end + 1))) {
        i = end + 1;
        continue;
      }
    }
    result += text.charAt(i);
    i++;
  }
  return result;
};

export const stripToolCallNoise = (text: string): string => {
  let out = text.replace(TOOL_CALL_TAG_RE, "");
  out = out.replace(FENCE_RE, (full, inner: string) =>
    isToolCallObject(inner) ? "" : full,
  );
  out = stripBareToolCalls(out);
  out = out.replace(STRAY_TAG_RE, "");
  // Collapse the blank-line gaps left by removals.
  return out.replace(/\n{3,}/g, "\n\n").trim();
};
