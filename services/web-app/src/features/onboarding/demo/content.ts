/**
 * Содержимое демо-проекта: исходник, ответы ИИ, замечания и git. Это данные
 * сценария, а не тексты интерфейса, поэтому лежат здесь, в ленивом чанке, а не в
 * словарях основного бандла. Оба языка обязаны совпадать по форме (тест).
 */

export type DemoComment = {
  id: string;
  author: string;
  /** Кто оставил: руководитель или ИИ-проверка. */
  kind: "supervisor" | "agent";
  quote: string;
  text: string;
};

export type DemoPrompt = { id: "check" | "shorten"; label: string };

export type DemoContent = {
  projectName: string;
  templateFallback: string;
  author: string;
  placeholderTopic: string;
  topic: string;
  source: (title: string, author: string) => string;
  buildLog: string[];
  prompts: DemoPrompt[];
  /** Ответ ИИ на каждую подсказку: потоком, по словам. */
  replies: Record<DemoPrompt["id"], string>;
  agentComments: DemoComment[];
  supervisorComment: DemoComment;
  remoteUrl: string;
  commitMessages: { edit: string; review: string };
  previewFooter: string;
};

const sourceRu = (
  title: string,
  author: string,
) => `\\documentclass{hse-coursework}

\\title{${title}}
\\author{${author}}

\\begin{document}
\\maketitle

\\begin{abstract}
В работе рассматривается задача автоматизации учёта посещаемости
занятий. Описаны требования, архитектура и прототип системы.
\\end{abstract}

\\section{Введение}
Учёт посещаемости в университете до сих пор часто ведётся
на бумаге. Это отнимает время преподавателя и приводит к ошибкам.

\\section{Анализ требований}
Мы опросили преподавателей и студентов и выделили
основные сценарии работы системы.

\\end{document}
`;

const sourceEn = (
  title: string,
  author: string,
) => `\\documentclass{hse-coursework}

\\title{${title}}
\\author{${author}}

\\begin{document}
\\maketitle

\\begin{abstract}
This work addresses automating class attendance tracking.
It describes the requirements, the architecture and a prototype.
\\end{abstract}

\\section{Introduction}
Attendance at the university is still often tracked
on paper. It takes the teacher's time and leads to mistakes.

\\section{Requirements analysis}
We interviewed teachers and students and identified
the main scenarios of the system.

\\end{document}
`;

const RU: DemoContent = {
  projectName: "Демо: курсовая работа",
  templateFallback: "Курсовая работа",
  author: "Иван Студентов",
  placeholderTopic: "Тема вашей работы",
  topic: "Система учёта посещаемости занятий",
  source: sourceRu,
  buildLog: [
    "Подготовка проекта…",
    "xelatex main.tex (проход 1 из 2)",
    "biber main",
    "xelatex main.tex (проход 2 из 2)",
    "Готово: main.pdf, 2 страницы",
  ],
  prompts: [
    { id: "check", label: "Проверь введение на ошибки и стиль" },
    { id: "shorten", label: "Сделай аннотацию короче" },
  ],
  replies: {
    check:
      "Прочитал введение. Нашёл два места, которые стоит поправить: «до сих пор часто» звучит разговорно, а утверждение про ошибки лучше подкрепить источником. Оставил замечания на полях, их видно в панели замечаний.",
    shorten:
      "Предлагаю такую аннотацию: «Работа посвящена автоматизации учёта посещаемости: требования, архитектура, прототип». Оставил предложение замечанием, примите его, если нравится.",
  },
  agentComments: [
    {
      id: "c-style",
      author: "ИИ-агент",
      kind: "agent",
      quote: "до сих пор часто ведётся",
      text: "Разговорный оборот. Вариант: «нередко ведётся».",
    },
    {
      id: "c-source",
      author: "ИИ-агент",
      kind: "agent",
      quote: "приводит к ошибкам",
      text: "Утверждение без источника. Добавьте ссылку или данные опроса.",
    },
  ],
  supervisorComment: {
    id: "c-supervisor",
    author: "Руководитель",
    kind: "supervisor",
    quote: "Анализ требований",
    text: "Добавьте таблицу с ролями пользователей.",
  },
  remoteUrl: "https://github.com/ivan-studentov/kursovaya.git",
  commitMessages: {
    edit: "Тема работы и введение",
    review: "Правки по замечаниям",
  },
  previewFooter: "Москва 2026",
};

const EN: DemoContent = {
  projectName: "Demo: coursework",
  templateFallback: "Coursework",
  author: "Ivan Studentov",
  placeholderTopic: "Your thesis topic",
  topic: "Class attendance tracking system",
  source: sourceEn,
  buildLog: [
    "Preparing the project…",
    "xelatex main.tex (pass 1 of 2)",
    "biber main",
    "xelatex main.tex (pass 2 of 2)",
    "Done: main.pdf, 2 pages",
  ],
  prompts: [
    { id: "check", label: "Check the introduction for mistakes and style" },
    { id: "shorten", label: "Make the abstract shorter" },
  ],
  replies: {
    check:
      "I read the introduction. Two places are worth fixing: “still often” sounds informal, and the claim about mistakes needs a source. I left comments in the margin, see the comments panel.",
    shorten:
      "Here is a shorter abstract: “The work automates attendance tracking: requirements, architecture, prototype.” I left it as a comment, accept it if you like it.",
  },
  agentComments: [
    {
      id: "c-style",
      author: "AI agent",
      kind: "agent",
      quote: "still often tracked",
      text: "Informal wording. Try “is frequently tracked”.",
    },
    {
      id: "c-source",
      author: "AI agent",
      kind: "agent",
      quote: "leads to mistakes",
      text: "A claim without a source. Add a reference or survey data.",
    },
  ],
  supervisorComment: {
    id: "c-supervisor",
    author: "Supervisor",
    kind: "supervisor",
    quote: "Requirements analysis",
    text: "Add a table with the user roles.",
  },
  remoteUrl: "https://github.com/ivan-studentov/coursework.git",
  commitMessages: {
    edit: "Topic and introduction",
    review: "Fixes after review",
  },
  previewFooter: "Moscow 2026",
};

export const DEMO_CONTENT: Record<"ru" | "en", DemoContent> = {
  ru: RU,
  en: EN,
};

export const demoContentFor = (lang: string): DemoContent =>
  lang === "en" ? EN : RU;
