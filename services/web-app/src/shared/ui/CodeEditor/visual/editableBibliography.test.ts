import { describe, expect, it } from "vitest";
import {
  addEntry,
  hasEmptyKey,
  moveEntry,
  parseEditableBibliography,
  removeEntry,
  sanitizeKey,
  serializeEditableBibliography,
  setEntryKey,
  setEntryValue,
  type ParsedBibliography,
} from "./editableBibliography";

const GOST = String.raw`\begin{thebibliography}{99}
\bibitem{gost19101}
ГОСТ 19.101-77: Виды программ и программных документов. // ЕСПД. — М.: ИПК, 2001.

\bibitem{gost19102}
ГОСТ 19.102-77: Стадии разработки. // ЕСПД. — М.: ИПК, 2001.

\bibitem{gost19103}
ГОСТ 19.103-77: Обозначения программ. // ЕСПД. — М.: ИПК, 2001.
\end{thebibliography}`;

const parsed = (source: string): ParsedBibliography => {
  const result = parseEditableBibliography(source);
  if (!result) throw new Error("expected a bibliography");
  return result;
};

describe("parseEditableBibliography", () => {
  it("returns null for non-bibliography source", () => {
    expect(parseEditableBibliography(undefined)).toBeNull();
    expect(parseEditableBibliography("Обычный текст")).toBeNull();
    expect(
      parseEditableBibliography(
        String.raw`\begin{itemize}\item a\end{itemize}`,
      ),
    ).toBeNull();
  });

  it("requires the width group and a matching end", () => {
    expect(
      parseEditableBibliography(
        String.raw`\begin{thebibliography}\bibitem{a} x`,
      ),
    ).toBeNull();
    expect(
      parseEditableBibliography(
        String.raw`\begin{thebibliography}{9}\bibitem{a} x`,
      ),
    ).toBeNull();
  });

  it("parses keys and reference text", () => {
    const { scaffold, draft } = parsed(GOST);
    expect(scaffold.editable).toBe(true);
    expect(scaffold.widthArg).toBe("99");
    expect(draft.entries.map((e) => e.key)).toEqual([
      "gost19101",
      "gost19102",
      "gost19103",
    ]);
    expect(draft.entries[0]?.value).toContain("ГОСТ 19.101-77");
    expect(draft.entries[0]?.value).not.toContain("\\bibitem");
  });

  it("round-trips an untouched bibliography to equivalent LaTeX", () => {
    const { scaffold, draft } = parsed(GOST);
    const output = serializeEditableBibliography(scaffold, draft);
    expect(output).toContain("\\begin{thebibliography}{99}");
    expect(output).toContain("\\end{thebibliography}");
    // Every original entry survives verbatim.
    expect(output).toContain("\\bibitem{gost19101}");
    expect(output).toContain(
      "ГОСТ 19.101-77: Виды программ и программных документов.",
    );
    expect(output).toContain("\\bibitem{gost19103}");
    // Re-parsing yields the same keys (idempotent structure).
    expect(parsed(output).draft.entries.map((e) => e.key)).toEqual([
      "gost19101",
      "gost19102",
      "gost19103",
    ]);
  });

  it("edits a value, keeping the others byte-for-byte", () => {
    const { scaffold, draft } = parsed(GOST);
    const next = setEntryValue(draft, 1, "Изменённый источник.");
    const output = serializeEditableBibliography(scaffold, next);
    expect(output).toContain("\\bibitem{gost19102}\nИзменённый источник.");
    // Untouched neighbours keep their exact original body.
    expect(output).toContain(
      "ГОСТ 19.101-77: Виды программ и программных документов.",
    );
    expect(output).toContain("ГОСТ 19.103-77: Обозначения программ.");
  });

  it("edits a key without touching the body", () => {
    const { scaffold, draft } = parsed(GOST);
    const output = serializeEditableBibliography(
      scaffold,
      setEntryKey(draft, 0, "gost-19-101"),
    );
    expect(output).toContain("\\bibitem{gost-19-101}");
    expect(output).not.toContain("\\bibitem{gost19101}");
    expect(output).toContain(
      "ГОСТ 19.101-77: Виды программ и программных документов.",
    );
  });

  it("adds, removes and moves entries", () => {
    const { scaffold, draft } = parsed(GOST);

    const added = addEntry(draft);
    expect(added.entries).toHaveLength(4);
    const addedOut = serializeEditableBibliography(
      scaffold,
      setEntryValue(setEntryKey(added, 3, "newref"), 3, "Новый источник."),
    );
    expect(addedOut).toContain("\\bibitem{newref}\nНовый источник.");

    const removed = removeEntry(draft, 1);
    expect(removed.entries.map((e) => e.key)).toEqual([
      "gost19101",
      "gost19103",
    ]);
    expect(serializeEditableBibliography(scaffold, removed)).not.toContain(
      "gost19102",
    );

    const moved = moveEntry(draft, 2, 0);
    expect(moved.entries.map((e) => e.key)).toEqual([
      "gost19103",
      "gost19101",
      "gost19102",
    ]);
  });

  it("preserves an optional \\bibitem[label]{key}", () => {
    const src = String.raw`\begin{thebibliography}{9}
\bibitem[ГОСТ]{gost} Текст источника.
\end{thebibliography}`;
    const { scaffold, draft } = parsed(src);
    expect(draft.entries[0]?.optLabel).toBe("ГОСТ");
    expect(serializeEditableBibliography(scaffold, draft)).toContain(
      "\\bibitem[ГОСТ]{gost}",
    );
  });

  it("keeps \\textbf markup in a reference body round-trip", () => {
    const src = String.raw`\begin{thebibliography}{9}
\bibitem{k} \textbf{Автор} Название. — М., 2020.
\end{thebibliography}`;
    const { scaffold, draft } = parsed(src);
    expect(draft.entries[0]?.value).toContain("\\textbf{Автор}");
    expect(serializeEditableBibliography(scaffold, draft)).toContain(
      "\\textbf{Автор}",
    );
  });
});

describe("round-trip regressions (adversarial review)", () => {
  it("round-trips an untouched bibliography BYTE-for-byte and is idempotent", () => {
    const { scaffold, draft } = parsed(GOST);
    const once = serializeEditableBibliography(scaffold, draft);
    expect(once).toBe(GOST); // no separator doubling, no drift
    // Re-parse + re-serialize any number of times: stable (no blank-line growth).
    let text = GOST;
    for (let i = 0; i < 4; i += 1) {
      const round = parsed(text);
      text = serializeEditableBibliography(round.scaffold, round.draft);
    }
    expect(text).toBe(GOST);
  });

  it("does not grow blank lines when one entry is edited repeatedly", () => {
    let text = GOST;
    for (let i = 0; i < 5; i += 1) {
      const { scaffold, draft } = parsed(text);
      text = serializeEditableBibliography(
        scaffold,
        setEntryValue(draft, 0, `Издание ${String(i)}.`),
      );
    }
    // The gap before a downstream untouched entry stays a single blank line.
    expect(text).toContain("\n\n\\bibitem{gost19102}");
    expect(text).not.toContain("\n\n\n\\bibitem{gost19102}");
  });

  it("does NOT split an entry whose body quotes a literal \\bibitem", () => {
    const src = String.raw`\begin{thebibliography}{9}
\bibitem{a} On using \bibitem{nested} inside prose, see p.5.
\bibitem{b} Second.
\end{thebibliography}`;
    const { draft } = parsed(src);
    expect(draft.entries.map((e) => e.key)).toEqual(["a", "b"]);
    expect(draft.entries[0]?.value).toContain("\\bibitem{nested}");
  });

  it("sanitizes an edited key so a stray brace can't unbalance the env", () => {
    const { scaffold, draft } = parsed(GOST);
    const out = serializeEditableBibliography(
      scaffold,
      setEntryKey(draft, 0, "smith}2020\\evil%"),
    );
    expect(out).toContain("\\bibitem{smith2020evil}");
    // Braces stay balanced across the whole environment.
    const opens = (out.match(/(?<!\\)\{/g) ?? []).length;
    const closes = (out.match(/(?<!\\)\}/g) ?? []).length;
    expect(opens).toBe(closes);
  });

  it("flags an empty key and never emits it silently on serialize", () => {
    const { draft } = parsed(GOST);
    expect(hasEmptyKey(draft)).toBe(false);
    const added = addEntry(draft);
    expect(hasEmptyKey(added)).toBe(true);
    expect(hasEmptyKey(setEntryKey(added, 3, "  "))).toBe(true);
    expect(hasEmptyKey(setEntryKey(added, 3, "ok"))).toBe(false);
  });

  it("preserves a comment inside an untouched bibliography on round-trip", () => {
    const src = String.raw`\begin{thebibliography}{9}
% источники по ГОСТ
\bibitem{a} Первый.
% \bibitem{old} закомментированный
\bibitem{b} Второй.
\end{thebibliography}`;
    const { scaffold, draft } = parsed(src);
    // The commented-out \bibitem is NOT a real entry.
    expect(draft.entries.map((e) => e.key)).toEqual(["a", "b"]);
    const out = serializeEditableBibliography(scaffold, draft);
    expect(out).toBe(src); // comments survive verbatim
    expect(out).toContain("% источники по ГОСТ");
    expect(out).toContain("% \\bibitem{old}");
  });

  it("sanitizeKey strips exactly the LaTeX-breaking characters", () => {
    expect(sanitizeKey("a{b}c\\d%e#f~g^h$i,j k")).toBe("abcdefghijk");
    expect(sanitizeKey("gost19101")).toBe("gost19101");
    expect(sanitizeKey("ref-2020")).toBe("ref-2020");
  });

  it("does NOT merge entries when a raw % sits inside a \\url{}", () => {
    const src = String.raw`\begin{thebibliography}{99}
\bibitem{a} Первый. \url{https://arch.org/id%2Fx}
\bibitem{b} Второй.
\end{thebibliography}`;
    const { scaffold, draft } = parsed(src);
    // The % inside \url{} must not swallow the brace and merge \bibitem{b}.
    expect(draft.entries.map((e) => e.key)).toEqual(["a", "b"]);
    expect(draft.entries[0]?.value).toContain("id%2Fx");
    // Untouched still round-trips byte-for-byte, and editing keeps both entries.
    expect(serializeEditableBibliography(scaffold, draft)).toBe(src);
    const edited = serializeEditableBibliography(
      scaffold,
      setEntryValue(draft, 0, "Изменённый первый."),
    );
    expect(edited).toContain("\\bibitem{b}");
  });

  it("keeps a real line-start comment a comment (not a verbatim span)", () => {
    const src = String.raw`\begin{thebibliography}{9}
% \url{http://x} — заметка
\bibitem{a} Первый.
\end{thebibliography}`;
    const { scaffold, draft } = parsed(src);
    expect(draft.entries.map((e) => e.key)).toEqual(["a"]);
    expect(serializeEditableBibliography(scaffold, draft)).toBe(src);
  });

  it("ignores a \\bibitem inside a \\begin{verbatim} block", () => {
    const src = String.raw`\begin{thebibliography}{9}
\bibitem{a} код:
\begin{verbatim}
\bibitem{fake} не источник
\end{verbatim}
\bibitem{b} Второй.
\end{thebibliography}`;
    const { scaffold, draft } = parsed(src);
    // The verbatim \bibitem{fake} is code, not a phantom entry.
    expect(draft.entries.map((e) => e.key)).toEqual(["a", "b"]);
    expect(serializeEditableBibliography(scaffold, draft)).toBe(src);
  });

  it("does not merge entries across a two-arg \\href or a literal brace", () => {
    const href = String.raw`\begin{thebibliography}{9}
\bibitem{a} See \href{http://x/a%2Fb}{display % text} end.
\bibitem{b} Второй.
\end{thebibliography}`;
    expect(parsed(href).draft.entries.map((e) => e.key)).toEqual(["a", "b"]);

    const verb = String.raw`\begin{thebibliography}{9}
\bibitem{a} код \verb|{| здесь
\bibitem{b} Второй.
\end{thebibliography}`;
    const parsedVerb = parsed(verb);
    expect(parsedVerb.draft.entries.map((e) => e.key)).toEqual(["a", "b"]);
    // Untouched still round-trips byte-for-byte.
    expect(
      serializeEditableBibliography(parsedVerb.scaffold, parsedVerb.draft),
    ).toBe(verb);
  });
});
