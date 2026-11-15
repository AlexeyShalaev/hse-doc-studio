import type {
  Completion,
  CompletionContext,
  CompletionResult,
  CompletionSource,
} from "@codemirror/autocomplete";
import { EditorState, type Extension } from "@codemirror/state";
import type { PackEditorHints } from "@entities/pack-studio";
import { i18n, pickLocalized } from "@shared/lib";

// Автодополнение шаблонов пака (template-studio.md, 5.4): переменные контекста
// build_context и фильтры внутри {{ }} и ((* *)), макросы \hse... динамических
// инклудов версии в LaTeX. Источник подключается через languageData состояния,
// поэтому складывается с собственными подсказками грамматики LaTeX и YAML.

/** Переменные контекста рендера пака (infra/project_init/template_renderer.build_context). */
export const JINJA_CONTEXT: readonly string[] = [
  "project.name",
  "project.lang",
  "project.kind",
  "project.staffing",
  "project.authors",
  "project.meta",
  "project.created_at",
  ...["supervisor", "co_supervisor", "academic_supervisor"].flatMap((person) =>
    ["name", "role", "title", "degree"].map((f) => `project.${person}.${f}`),
  ),
  ...["name", "group", "email", "slug", "topic", "meta"].map(
    (f) => `author.${f}`,
  ),
  "team.is_team",
  "team.is_shared_base",
  "pack.id",
  "template.id",
  "template.version",
  "build.year",
  "build.date",
];

/** Фильтры пака (PACK_FILTERS) и частые встроенные фильтры Jinja. */
export const JINJA_FILTERS: readonly string[] = [
  "texesc",
  "xmlesc",
  "default",
  "trim",
  "upper",
  "lower",
  "capitalize",
  "title",
  "replace",
  "join",
  "length",
  "first",
  "last",
  "int",
  "string",
];

/** Ключевые слова блоков ((* ... *)). */
export const JINJA_KEYWORDS: readonly string[] = [
  "if",
  "elif",
  "else",
  "endif",
  "for",
  "endfor",
  "set",
];

const lastOpen = (text: string, open: string, close: string): boolean =>
  text.lastIndexOf(open) > text.lastIndexOf(close);

/** Курсор внутри выражения Jinja: открыт {{ или ((* и не закрыт до курсора в этой строке. */
export const insideJinja = (linePrefix: string): boolean =>
  lastOpen(linePrefix, "{{", "}}") || lastOpen(linePrefix, "((*", "*))");

const t = (key: string, options: Record<string, unknown> = {}): string =>
  i18n.t(`packStudio:completion.${key}`, options);

const variableOptions = (hints: PackEditorHints | null): Completion[] => {
  const lang = i18n.language;
  const fields = (hints?.meta_fields ?? []).map((field): Completion => {
    const info = [field.type, field.group].filter(Boolean).join(" · ");
    return {
      label: `project.meta.${field.key}`,
      type: "property",
      detail: field.label ? pickLocalized(field.label, lang, field.key) : "",
      ...(info ? { info } : {}),
      boost: 2,
    };
  });
  return [
    ...fields,
    ...JINJA_CONTEXT.map((name): Completion => ({
      label: name,
      type: "variable",
      detail: t("context"),
    })),
  ];
};

const jinjaSource =
  (getHints: () => PackEditorHints | null): CompletionSource =>
  (context: CompletionContext): CompletionResult | null => {
    const line = context.state.doc.lineAt(context.pos);
    const prefix = line.text.slice(0, context.pos - line.from);
    if (!insideJinja(prefix)) return null;

    const filter = /\|\s*([A-Za-z_]\w*)?$/.exec(prefix);
    if (filter) {
      const word = filter[1] ?? "";
      return {
        from: context.pos - word.length,
        options: JINJA_FILTERS.map((name) => ({
          label: name,
          type: "function",
          detail: t("filter"),
        })),
        validFor: /^\w*$/,
      };
    }
    const block = /\(\(\*-?\s*([a-z]*)$/.exec(prefix);
    if (block) {
      const word = block[1] ?? "";
      return {
        from: context.pos - word.length,
        options: JINJA_KEYWORDS.map((name) => ({
          label: name,
          type: "keyword",
        })),
        validFor: /^[a-z]*$/,
      };
    }
    const word = context.matchBefore(/[A-Za-z_][\w.]*$/);
    if (!word && !context.explicit) return null;
    return {
      from: word?.from ?? context.pos,
      options: variableOptions(getHints()),
      validFor: /^[\w.]*$/,
    };
  };

const macroSource =
  (getHints: () => PackEditorHints | null): CompletionSource =>
  (context: CompletionContext): CompletionResult | null => {
    const macros = getHints()?.macros ?? [];
    if (macros.length === 0) return null;
    const token = context.matchBefore(/\\[A-Za-z]*/);
    if (!token || (token.from === token.to && !context.explicit)) return null;
    const prefix = context.state.doc.sliceString(context.pos - 1, context.pos);
    if (prefix !== "\\" && !/[A-Za-z]/.test(prefix)) return null;
    return {
      from: token.from,
      options: macros.map((macro): Completion => ({
        label: `\\${macro.name}`,
        type: "function",
        detail:
          macro.keys.length > 0
            ? t("prints", { keys: macro.keys.join(", ") })
            : t("macro"),
        info: macro.source.split("/").slice(-2).join("/"),
        boost: 1,
      })),
      validFor: /^\\[A-Za-z]*$/,
    };
  };

export type PackCompletionOptions = {
  /** Свежие подсказки версии: читаются при каждом запросе, расширение создаётся один раз. */
  getHints: () => PackEditorHints | null;
  /** Шаблоны Jinja: файлы версии в files/ (`.j2` и тексты, которые рендерятся при создании проекта). */
  jinja: boolean;
  /** Макросы \hse...: LaTeX-исходники версии. */
  macros: boolean;
};

/** Источники автодополнения для редактора кода (через extraExtensions). */
export const packCompletionExtension = ({
  getHints,
  jinja,
  macros,
}: PackCompletionOptions): Extension => {
  const sources: CompletionSource[] = [];
  if (jinja) sources.push(jinjaSource(getHints));
  if (macros) sources.push(macroSource(getHints));
  if (sources.length === 0) return [];
  return EditorState.languageData.of(() =>
    sources.map((autocomplete) => ({ autocomplete })),
  );
};
