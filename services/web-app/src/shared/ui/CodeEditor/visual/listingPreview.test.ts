import { describe, expect, it } from "vitest";
import { parseListingPreview } from "./listingPreview";

describe("parseListingPreview", () => {
  it("returns a stable fallback while a source is unavailable", () => {
    expect(parseListingPreview(undefined)).toEqual({
      language: "",
      caption: "",
      label: "",
      code: "",
      complete: false,
      truncated: false,
    });
    expect(parseListingPreview("")).toEqual(parseListingPreview(undefined));
    expect(parseListingPreview("Обычный текст")).toEqual(
      parseListingPreview(undefined),
    );
  });

  it("parses common options and preserves the exact listing body", () => {
    const code = String.raw`
def hello(name: str):
    # 100% is still code here
    return f"Hello, {name}"
`;
    const source = `${String.raw`\begin{lstlisting}[language={Python}, caption={\textbf{Пример, функции}~№1}, label={lst:hello}]`}${code}${String.raw`\end{lstlisting}`}`;

    expect(parseListingPreview(source)).toEqual({
      language: "Python",
      caption: "Пример, функции №1",
      label: "lst:hello",
      code,
      complete: true,
      truncated: false,
    });
  });

  it("ignores a commented environment but keeps percent signs inside code", () => {
    const code = String.raw`
const percent = "100%";
\unknown{<img src=x onerror=alert(1)>}
`;
    const source = `${String.raw`% \begin{lstlisting}[language=Fake]
% ignored
% \end{lstlisting}
\begin{lstlisting}[language=TypeScript]`}${code}${String.raw`\end{lstlisting}`}`;
    const preview = parseListingPreview(source);

    expect(preview.language).toBe("TypeScript");
    expect(preview.code).toBe(code);
    expect(preview.code).toContain("<img src=x onerror=alert(1)>");
    expect(preview.complete).toBe(true);
  });

  it("returns useful inert content for an unclosed environment", () => {
    const source = String.raw`\begin{lstlisting}[language=C++]
int main() {
  return 0;
}`;

    expect(() => parseListingPreview(source)).not.toThrow();
    expect(parseListingPreview(source)).toMatchObject({
      language: "C++",
      code: "\nint main() {\n  return 0;\n}",
      complete: false,
      truncated: false,
    });
  });

  it("falls back safely when the option group is malformed", () => {
    const source = String.raw`\begin{lstlisting}[language={Python}
print("safe")
\end{lstlisting}`;
    const preview = parseListingPreview(source);

    expect(preview.language).toBe("");
    expect(preview.code).toContain("[language={Python}");
    expect(preview.code).toContain('print("safe")');
    expect(preview.complete).toBe(false);
  });

  // Границы две (MAX_CODE_LINES и MAX_CODE_LENGTH), и какая из них сработает —
  // решают данные: boundCode берёт минимум. На длинных строках первым упирается
  // лимит символов, поэтому одна фикстура проверить обе не может — она молча
  // измеряет только более тесную. Отсюда два случая.
  it("bounds the rendered line count when the lines are short", () => {
    const code = `\n${Array.from(
      { length: 800 },
      (_, index) => `line ${String(index + 1)}`,
    ).join("\n")}\n`;
    const source = `${String.raw`\begin{lstlisting}`}${code}${String.raw`\end{lstlisting}`}`;
    const preview = parseListingPreview(source);

    // ~7 КБ на 800 строк — до лимита символов далеко, режет именно счёт строк.
    expect(code.length).toBeLessThan(32_000);
    expect(preview.truncated).toBe(true);
    expect(preview.code.split(/\r\n|\r|\n/)).toHaveLength(500);
    expect(code.startsWith(preview.code)).toBe(true);
  });

  it("bounds the code length when the body outgrows the character cap", () => {
    const code = `\n${Array.from(
      { length: 20 },
      (_, index) => `line ${String(index + 1)} ${"x".repeat(4_000)}`,
    ).join("\n")}\n`;
    const source = `${String.raw`\begin{lstlisting}`}${code}${String.raw`\end{lstlisting}`}`;
    const preview = parseListingPreview(source);

    // Строк всего 20 — до лимита в 500 не дотянуть даже близко, режет длина.
    expect(preview.truncated).toBe(true);
    expect(preview.code).toHaveLength(32_000);
    expect(preview.code.split(/\r\n|\r|\n/).length).toBeLessThan(500);
    expect(code.startsWith(preview.code)).toBe(true);
  });
});
