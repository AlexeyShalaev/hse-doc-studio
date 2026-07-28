export type ChangelogEntry = {
  v: string;
  date: string;
  by: string;
  changes: readonly string[];
};

export const SAMPLE_CHANGELOG: readonly ChangelogEntry[] = [
  {
    v: "v0.7",
    date: "2026-05-22",
    by: "Шалаев И. А.",
    changes: [
      "Переписан раздел 4 — добавлены графики latency",
      "Исправлены опечатки в введении",
      "Подключён ai-usage/form.md",
    ],
  },
  {
    v: "v0.6",
    date: "2026-05-12",
    by: "Шалаев И. А.",
    changes: ["Чистовая версия после правок руководителя"],
  },
  {
    v: "v0.5",
    date: "2026-04-28",
    by: "Шалаев И. А.",
    changes: [
      "Добавлен раздел 3.4 «Метрики»",
      "Обновлены ссылки на ГОСТ 7.32-2017",
    ],
  },
  {
    v: "v0.4",
    date: "2026-04-10",
    by: "Шалаев И. А.",
    changes: ["Первичная сборка дипломной"],
  },
];

export type DocSignature = {
  name: string;
  role: string;
  who: string;
  status: "signed" | "pending" | "locked";
  date?: string;
};

export const DOC_SIGNATURES: readonly DocSignature[] = [
  {
    name: "Шалаев И. А.",
    role: "автор",
    who: "AUTHOR",
    status: "signed",
    date: "22.05.2026",
  },
  {
    name: "Иванов А. К.",
    role: "научный руководитель",
    who: "SUPERVISOR",
    status: "signed",
    date: "23.05.2026",
  },
  {
    name: "Петров В. Г.",
    role: "со-руководитель",
    who: "CO-SUPERVISOR",
    status: "pending",
  },
];

export const SAMPLE_TEX = `% vkr/main.tex
\\documentclass[14pt,a4paper]{extarticle}
\\input{../common/preamble}
\\input{../common/commands}

\\begin{document}
\\input{../common/title_template}

\\section*{Введение}
Современные системы анализа git-репозиториев сталкиваются с\\
рядом ограничений при обработке репозиториев глубиной свыше 10000 коммитов.
В данной работе рассматривается подход, позволяющий\\
снизить latency анализа на 35\\% относительно baseline.

\\section{Постановка задачи}
\\label{sec:problem}
Задача формализуется следующим образом:
\\begin{itemize}
  \\item Дан репозиторий $R$ с глубиной истории $|R| \\le 10^5$.
  \\item Требуется вычислить метрики diff-аналитики $M(R)$.
  \\item Latency не должна превышать $T = 200$ мс на 1000 коммитов.
\\end{itemize}

\\input{sections/02_review}
\\input{sections/03_architecture}
\\input{sections/04_implementation}
\\input{sections/05_metrics}

\\bibliographystyle{gost-numeric}
\\bibliography{references}

\\end{document}
`;
