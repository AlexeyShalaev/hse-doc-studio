import type { CiRequest } from "@entities/git-sync";

// Настройки автосборки, как их видит окно: всё, что можно выбрать, и перевод в
// запрос к серверу. Чистые функции, чтобы проверять без окна.

export type CiProvider = "github" | "gitlab";
export type CiPublish = "artifacts" | "release";
export type CiTrigger = "push" | "tag" | "manual";
export type CiDocsMode = "all" | "selected";

export const CI_PROVIDERS: readonly CiProvider[] = ["github", "gitlab"];
export const CI_PUBLISH: readonly CiPublish[] = ["artifacts", "release"];
export const CI_TRIGGERS: readonly CiTrigger[] = ["push", "tag", "manual"];

export type CiOptions = {
  provider: CiProvider;
  docsMode: CiDocsMode;
  docs: string[];
  publish: CiPublish;
  triggers: CiTrigger[];
  /** Пусто, пока образ не меняли: тогда сервер берёт образ текущей версии Студии. */
  image: string;
};

export const DEFAULT_CI_OPTIONS: CiOptions = {
  provider: "github",
  docsMode: "all",
  docs: [],
  publish: "artifacts",
  triggers: ["push"],
  image: "",
};

export type CiProblem = "no_documents" | "no_triggers";

/** Что мешает показать и записать файл; пусто, если настройки годятся. */
export const ciProblems = (options: CiOptions): CiProblem[] => {
  const problems: CiProblem[] = [];
  if (options.docsMode === "selected" && options.docs.length === 0) {
    problems.push("no_documents");
  }
  if (options.triggers.length === 0) problems.push("no_triggers");
  return problems;
};

export const toCiRequest = (options: CiOptions): CiRequest => {
  const image = options.image.trim();
  return {
    provider: options.provider,
    docs: options.docsMode === "all" ? "all" : options.docs,
    publish: options.publish,
    // Порядок фиксирован, чтобы тот же выбор давал тот же запрос и тот же файл.
    triggers: CI_TRIGGERS.filter((trigger) =>
      options.triggers.includes(trigger),
    ),
    ...(image === "" ? {} : { image }),
  };
};

export const toggleTrigger = (
  triggers: CiTrigger[],
  trigger: CiTrigger,
): CiTrigger[] =>
  triggers.includes(trigger)
    ? triggers.filter((item) => item !== trigger)
    : [...triggers, trigger];

export const toggleDoc = (docs: string[], id: string): string[] =>
  docs.includes(id) ? docs.filter((item) => item !== id) : [...docs, id];

/** Ключ запроса: два одинаковых набора настроек не гонят сервер дважды. */
export const ciRequestKey = (request: CiRequest): string =>
  JSON.stringify(request);

export type CiFileState = "new" | "same" | "differs";

export const ciFileState = (file: {
  exists: boolean;
  same: boolean;
}): CiFileState => {
  if (!file.exists) return "new";
  return file.same ? "same" : "differs";
};
