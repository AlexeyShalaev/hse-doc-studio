import { describe, expect, it } from "vitest";
import { parseBibliographyPreview } from "./bibliographyPreview";

describe("parseBibliographyPreview", () => {
  it("returns a stable fallback while a source is unavailable", () => {
    expect(parseBibliographyPreview(undefined)).toEqual({
      entries: [],
      complete: false,
      truncated: false,
    });
    expect(parseBibliographyPreview("")).toEqual(
      parseBibliographyPreview(undefined),
    );
    expect(parseBibliographyPreview("Обычный текст")).toEqual(
      parseBibliographyPreview(undefined),
    );
  });

  it("parses keys, optional labels, wrappers and URL commands", () => {
    const source = String.raw`\begin{thebibliography}{99}
\bibitem{gost}
ГОСТ~Р 7.0.100--2018. \textbf{Библиографическая запись}.

\bibitem[Статья]{article}
Иванов~И.~И. \textit{Название статьи}. 2026.

\bibitem{website}
Документация. \url{https://example.org/a\_b?x=1\&y=2}.
\end{thebibliography}`;

    expect(parseBibliographyPreview(source)).toEqual({
      entries: [
        {
          key: "gost",
          text: "ГОСТ Р 7.0.100--2018. Библиографическая запись.",
        },
        {
          key: "article",
          text: "Иванов И. И. Название статьи. 2026.",
        },
        {
          key: "website",
          text: "Документация. https://example.org/a_b?x=1&y=2.",
        },
      ],
      complete: true,
      truncated: false,
    });
  });

  it("drops comments, preserves escaped percent and unwraps nested text", () => {
    const source = String.raw`% \begin{thebibliography}{1}
% \bibitem{fake} Скрытая запись
\begin{thebibliography}{1}
\bibitem{safe}
Автор % служебный комментарий
\emph{Название \textbf{работы}}.~Готово на 100\%.
\end{thebibliography}`;
    const preview = parseBibliographyPreview(source);

    expect(preview.entries).toEqual([
      {
        key: "safe",
        text: "Автор Название работы. Готово на 100%.",
      },
    ]);
    expect(preview.complete).toBe(true);
  });

  it("skips malformed items and still parses the next valid entry", () => {
    const source = String.raw`\begin{thebibliography}{9}
\bibitem missing-key-group
This malformed item is ignored.
\bibitem{valid}
Доступная запись.
\end{thebibliography}`;

    expect(() => parseBibliographyPreview(source)).not.toThrow();
    expect(parseBibliographyPreview(source)).toMatchObject({
      entries: [{ key: "valid", text: "Доступная запись." }],
      complete: true,
      truncated: false,
    });
  });

  it("keeps parsed entries when the environment has no closing command", () => {
    const source = String.raw`\begin{thebibliography}{9}
\bibitem{unfinished}
Запись без конца.`;
    const preview = parseBibliographyPreview(source);

    expect(preview.entries).toEqual([
      { key: "unfinished", text: "Запись без конца." },
    ]);
    expect(preview.complete).toBe(false);
    expect(preview.truncated).toBe(false);
  });

  it("returns unknown markup only as an inert printable string", () => {
    const source = String.raw`\begin{thebibliography}{1}
\bibitem{xss}
<img src=x onerror=alert(1)> \unknown{Безопасный текст}
\end{thebibliography}`;
    const preview = parseBibliographyPreview(source);

    expect(preview.entries[0]?.text).toBe(
      "<img src=x onerror=alert(1)> Безопасный текст",
    );
    expect(typeof preview.entries[0]?.text).toBe("string");
  });

  it("bounds entry count and printable text length", () => {
    const items = Array.from(
      { length: 120 },
      (_, index) =>
        `${String.raw`\bibitem`}{key-${String(index)}} ${"Длинный текст ".repeat(150)}`,
    ).join("\n");
    const source = `${String.raw`\begin{thebibliography}{999}`}
${items}
${String.raw`\end{thebibliography}`}`;
    const preview = parseBibliographyPreview(source);

    expect(preview.entries).toHaveLength(100);
    expect(preview.entries[0]?.text.endsWith("…")).toBe(true);
    expect(
      Array.from(preview.entries[0]?.text ?? "").length,
    ).toBeLessThanOrEqual(1_000);
    expect(preview.truncated).toBe(true);
  });
});
