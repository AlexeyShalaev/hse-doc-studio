import { describe, expect, it } from "vitest";
import { parseFigurePreview } from "./figurePreview";

describe("parseFigurePreview", () => {
  it("returns an empty preview for missing source", () => {
    expect(parseFigurePreview(undefined)).toEqual({
      image: null,
      caption: null,
    });
  });

  it("extracts the image path and rendered caption", () => {
    const source = String.raw`
      \begin{figure}[H]
      \centering
      \includegraphics[width=0.8\textwidth]{img/schema.png}
      \caption{Схема \textbf{модуля} авторизации}
      \label{fig:schema}
      \end{figure}
    `;

    expect(parseFigurePreview(source)).toEqual({
      image: "img/schema.png",
      caption: "Схема модуля авторизации",
    });
  });

  it("ignores commented-out graphics and reads the short caption's full form", () => {
    const source = String.raw`
      \begin{figure}
      % \includegraphics{old/draft.png}
      \includegraphics{diagram.pdf}
      \caption[Кратко]{Полное~описание с \emph{акцентом} \ldots}
      \end{figure}
    `;

    expect(parseFigurePreview(source)).toEqual({
      image: "diagram.pdf",
      caption: "Полное описание с акцентом …",
    });
  });

  it("handles a figure without a graphic or caption", () => {
    const source = String.raw`
      \begin{figure}[h]
      \begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}
      \end{figure}
    `;

    expect(parseFigurePreview(source)).toEqual({ image: null, caption: null });
  });
});
