import type {
  PackPreviewDocument,
  PackPreviewOptions,
  StartPackPreviewRequest,
} from "@entities/pack-studio";
import { effectiveVariant, variantFits } from "@features/pack-preview";

// Запрос сборки предпросмотра по состоянию экрана «Результат» (срез F12). Условий здесь нет:
// документ, вариант и имя файла считает сервер, а клиент только раскладывает вводные экрана по
// ключам запроса (`combination` знает переключатели версии, вариант идёт отдельным полем).

/** Откуда берутся вводные сборки: текущие вводные экрана или файл сценария пака. */
export type PreviewSource =
  { kind: "inputs" } | { kind: "scenario"; id: string };

export const INPUTS_SOURCE: PreviewSource = { kind: "inputs" };

export const sameSource = (a: PreviewSource, b: PreviewSource): boolean =>
  a.kind === "inputs"
    ? b.kind === "inputs"
    : b.kind === "scenario" && a.id === b.id;

export type PreviewTargetInput = {
  options: PackPreviewOptions;
  document: string;
  source: PreviewSource;
  /** Вариант, который выбрал человек в панели; `null`: как во вводных или в сценарии. */
  variantPick: string | null;
  /** Вводные показанного результата целиком (сценарий экрана, изменения и умолчания). */
  inputs: Readonly<Record<string, string>>;
  /** Набор данных из адреса экрана; `null`: набор по умолчанию. */
  example: string | null;
  /** Набор данных показанного результата (запасной у вводных экрана). */
  shownExample: string | null;
  /** Язык, на котором сценарий собирается: `lang` его вводных, иначе умолчание версии. */
  scenarioLang: string | undefined;
};

export type PreviewTarget = {
  /** Документ в опциях предпросмотра; `null`: сервер его не собирает. */
  doc: PackPreviewDocument | null;
  /** Тело запроса; `null`, пока собирать нечего. */
  body: StartPackPreviewRequest | null;
  /** Вариант, который уйдёт в сборку; `null`: у документа вариантов нет или берётся из сценария. */
  variant: string | null;
  /** Язык, по которому выбираются доступные варианты. */
  lang: string | undefined;
  /** Ключ запроса: по нему автосборка видит, что запрос изменился. */
  key: string;
};

/** Переключатели версии со значениями из вводных экрана: незнакомое значение сервер не принял бы. */
const combinationOf = (
  options: PackPreviewOptions,
  inputs: Readonly<Record<string, string>>,
): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const sw of options.switches) {
    const value = inputs[sw.id];
    if (value !== undefined && sw.values.includes(value)) out[sw.id] = value;
  }
  return out;
};

export const previewTarget = (input: PreviewTargetInput): PreviewTarget => {
  const { options, document, source, variantPick, inputs } = input;
  const doc = options.documents.find((d) => d.id === document) ?? null;
  const scenario = source.kind === "scenario";
  const lang = scenario ? input.scenarioLang : inputs.lang;
  if (doc === null) {
    return { doc, body: null, variant: null, lang, key: "" };
  }

  let variant: string | null;
  if (scenario) {
    // Без выбора вариант берёт сервер из вводной `variant.<документ>` сценария.
    const picked = (doc.variants ?? []).find((v) => v.id === variantPick);
    variant = picked && variantFits(picked, lang) ? picked.id : null;
  } else {
    variant = effectiveVariant(
      doc,
      variantPick ?? inputs[`variant.${document}`],
      lang,
    );
  }

  const body: StartPackPreviewRequest = {
    documents: [document],
    ...(scenario
      ? {
          scenario: source.id,
          ...(input.example && { example: input.example }),
        }
      : {
          example:
            input.example ?? input.shownExample ?? options.default_example,
          combination: combinationOf(options, inputs),
        }),
    ...(variant !== null && { variant }),
  };
  return { doc, body, variant, lang, key: JSON.stringify(body) };
};

/**
 * Что изменилось после сборки, кроме вводных: ревизия манифестов результата, файл сценария и
 * счётчик записей файлов пространства. Входит в ключ запуска, но не в тело запроса.
 */
export const filesKeyOf = (parts: {
  revision: string;
  scenarioEtag: string;
  filesRevision: number;
}): string =>
  [parts.revision, parts.scenarioEtag, String(parts.filesRevision)].join("|");

/** Ключ запуска: запрос и состояние файлов. Пустой, пока собирать нечего. */
export const runKeyOf = (target: PreviewTarget, filesKey: string): string =>
  target.body ? `${target.key}#${filesKey}` : "";

/** Сборка устарела из-за файлов, а не вводных: часть ключа после `#` не совпала. */
export const staleByFiles = (builtKey: string, filesKey: string): boolean =>
  builtKey.slice(builtKey.indexOf("#")) !== `#${filesKey}`;
