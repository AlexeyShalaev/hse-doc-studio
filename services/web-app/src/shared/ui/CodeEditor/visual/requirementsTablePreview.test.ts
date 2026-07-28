import { describe, expect, it } from "vitest";
import { parseRequirementsTablePreview } from "./requirementsTablePreview";

const ACTUAL_SHAPE = String.raw`
  % A comment with a fake row: BAD & BAD & BAD & BAD \\
  \begin{longtable}{|l|p{0.28\textwidth}|p{0.28\textwidth}|p{0.22\textwidth}|}
  \caption{Требования к функциональным характеристикам системы} \label{tab:requirements} \\
  \hline
  \textbf{№} & \textbf{Пользовательская история} & \textbf{Требование} & \textbf{Область} \\
  \hline
  \endfirsthead
  \multicolumn{4}{l}{Продолжение таблицы \thetable} \\
  \hline
  \textbf{№} & \textbf{Пользовательская история} & \textbf{Требование} & \textbf{Область} \\
  \hline
  \endhead
  \hline
  \endfoot
  \hline
  \endlastfoot
  ТЗ-Ф-01 & Как пользователь, я~хочу \ldots, чтобы \ldots & \req{ТЗ-Ф-01}{Система должна …} & Ядро \\[0.4cm]
  \hline
  ТЗ-Ф-02 & Вторая история & \req{ТЗ-Ф-02}{Второе требование} & API \\
  \hline
  \end{longtable}
`;

describe("parseRequirementsTablePreview", () => {
  it("returns a safe empty model for missing or malformed source", () => {
    const missing = parseRequirementsTablePreview(undefined);
    expect(missing).toEqual({
      caption: "Требования к функциональным характеристикам системы",
      headers: ["№", "Пользовательская история", "Требование", "Область"],
      rows: [],
    });
    expect(parseRequirementsTablePreview("\\begin{longtable}{broken")).toEqual(
      missing,
    );
  });

  it("reads caption, four headers, and data rows from a longtable", () => {
    const preview = parseRequirementsTablePreview(ACTUAL_SHAPE);

    expect(preview.caption).toBe(
      "Требования к функциональным характеристикам системы",
    );
    expect(preview.headers).toEqual([
      "№",
      "Пользовательская история",
      "Требование",
      "Область",
    ]);
    expect(preview.rows).toEqual([
      {
        id: "ТЗ-Ф-01",
        userStory: "Как пользователь, я хочу …, чтобы …",
        requirement: "Система должна …",
        area: "Ядро",
      },
      {
        id: "ТЗ-Ф-02",
        userStory: "Вторая история",
        requirement: "Второе требование",
        area: "API",
      },
    ]);
  });

  it("excludes repeated longtable headers and control rows", () => {
    const preview = parseRequirementsTablePreview(ACTUAL_SHAPE);
    expect(preview.rows).toHaveLength(2);
    expect(preview.rows.some((row) => row.id === "№")).toBe(false);
    expect(preview.rows.some((row) => row.id.includes("Продолжение"))).toBe(
      false,
    );
  });

  it("handles multiline cells, nested braces, comments, and escaped ampersands", () => {
    const source = String.raw`
      \begin{longtable}{|l|l|l|l|}
      \caption[Кратко]{Полные {функциональные} требования} \\
      \textbf{Код} & \textbf{История} & \textbf{Описание} & \textbf{Зона} \\
      \endfirsthead
      \endhead
      \endfoot
      \endlastfoot
      ТЗ-Ф-10 & Пользователь A \& B
        хочет результат &
        \req{ТЗ-Ф-10}{Система должна поддерживать
          \textbf{вложенный {текст}} и \ldots} &
        UI % trailing comment with & and \\
        \\
      \end{longtable}
    `;

    expect(parseRequirementsTablePreview(source)).toEqual({
      caption: "Полные функциональные требования",
      headers: ["Код", "История", "Описание", "Зона"],
      rows: [
        {
          id: "ТЗ-Ф-10",
          userStory: "Пользователь A & B хочет результат",
          requirement: "Система должна поддерживать вложенный текст и …",
          area: "UI",
        },
      ],
    });
  });

  it("uses the req id only when the visible id cell is empty", () => {
    const source = String.raw`
      \begin{longtable}{llll}
      № & История & Требование & Область \\
      \endfirsthead\endhead\endfoot\endlastfoot
      & История & \req{ТЗ-Ф-77}{Текст требования} & Backend \\
      \end{longtable}
    `;

    expect(parseRequirementsTablePreview(source).rows[0]).toEqual({
      id: "ТЗ-Ф-77",
      userStory: "История",
      requirement: "Текст требования",
      area: "Backend",
    });
  });

  it("parses a simple table without longtable head and foot controls", () => {
    const source = String.raw`
      \begin{tabularx}{\textwidth}{llll}
      \textbf{ID} & \textbf{Story} & \textbf{Requirement} & \textbf{Area} \\
      R-1 & Story & \req{R-1}{Must work} & Core \\
      \end{tabularx}
    `;

    expect(parseRequirementsTablePreview(source)).toMatchObject({
      headers: ["ID", "Story", "Requirement", "Area"],
      rows: [
        {
          id: "R-1",
          userStory: "Story",
          requirement: "Must work",
          area: "Core",
        },
      ],
    });
  });
});
