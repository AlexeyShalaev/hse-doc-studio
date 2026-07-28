/**
 * Appends a `% hse-noqa: <ruleId>` suppression comment to the 1-based `line`,
 * so the backend drops just that finding (not the whole rule). Mirrors the
 * marker parsed by the backend's `line_suppresses_rule`. CRLF-safe.
 */
export const insertSuppression = (
  content: string,
  line: number,
  ruleId: string,
): string => {
  const lines = content.split("\n");
  const index = line - 1;
  const raw = lines[index];
  if (raw === undefined) return content;
  const hasCR = raw.endsWith("\r");
  const body = hasCR ? raw.slice(0, -1) : raw;
  lines[index] = `${body}  % hse-noqa: ${ruleId}${hasCR ? "\r" : ""}`;
  return lines.join("\n");
};
