import type { TFunction } from "i18next";
import type { OutcomeFinding } from "@entities/pack-studio";
import type { Naming } from "./naming";

// Находки линтера результата человеческими словами (pack-studio-ux.md, 5.7 и принцип P5): по коду
// правила выбирается понятный заголовок и «Как исправить», а сообщение, подсказка и идентификаторы
// сервера уходят в «Технические подробности». Сервер отдаёт текст на русском и с внутренними
// словами; части находки (названия в «», числа, языки) достаются из текста и из затронутых частей
// результата. Чего достать не удалось, заменяется нейтральным словом.

/** Коды правил линтера результата; тест сверяет их с `RULES` сервера. */
export const LINT_RULES = [
  "slot-never-routed",
  "route-step-without-person",
  "route-gap",
  "visible-if-unknown-field",
  "visible-if-value-not-in-options",
  "required-hidden",
  "field-never-visible",
  "variant-lang-outside-langs",
  "skip-if-nda-without-nda",
  "when-unknown-person",
  "when-never-held",
  "when-always-held",
  "slot-when-overlap",
  "document-never-active",
  "item-never-active",
  "point-empty",
  "translation-missing",
  "builtin-gate-mismatch",
  "dimension-no-effect",
  "jinja-fail-open",
  "jinja-unknown-meta-key",
  "atlas-skipped",
] as const;
export type LintRule = (typeof LINT_RULES)[number];

export const isLintRule = (id: string): id is LintRule =>
  (LINT_RULES as readonly string[]).includes(id);

export type PlainFinding = {
  title: string;
  /** «Как исправить». */
  how: string;
  /** Дополнение к заголовку (в скольких случаях видно), если сервер его назвал. */
  extra: string | null;
  /** Правило известно слою формулировок; иначе заголовок это текст сервера. */
  known: boolean;
  tech: { label: string; value: string }[];
};

const quotedOf = (text: string): string[] =>
  [...text.matchAll(/«([^»]*)»/g)].map((match) => match[1] ?? "");

/** «в 4 из 12 строк»: сколько случаев из скольких. */
const shareOf = (text: string): { n: string; total: string } | null => {
  const match = /в\s+(\d+)\s+из\s+(\d+)/.exec(text);
  return match?.[1] && match[2] ? { n: match[1], total: match[2] } : null;
};

const listAfter = (text: string, pattern: RegExp): string[] =>
  (pattern.exec(text)?.[1] ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");

const fileDocument = (file: string | null): string | null =>
  file === null ? null : (/^files\/([^/!]+)\//.exec(file)?.[1] ?? null);

type Parts = { key: string; params: Record<string, string>; share?: boolean };

const pointerEnds = (finding: OutcomeFinding, tail: string): boolean =>
  (finding.pointer ?? "").endsWith(tail);

/** Вариант и подстановки для текстов правила. */
const partsOf = (
  finding: OutcomeFinding,
  naming: Naming,
  t: TFunction,
): Parts => {
  const { message } = finding;
  const q = quotedOf(message);
  const at = (index: number): string => q[index] ?? "";
  const nothing = { key: finding.rule_id, params: {} };
  switch (finding.rule_id) {
    case "slot-never-routed":
      return { ...nothing, params: { signature: naming.slot(at(0)) } };
    case "route-step-without-person": {
      const people = listAfter(message, /нет в проекте:\s*(.+?)\s*\(в \d+/)
        .map((id) => naming.role(id))
        .join(", ");
      return {
        ...nothing,
        params: {
          point: naming.point(at(0)),
          people: people === "" ? t("plain.fallback.role") : people,
        },
        share: true,
      };
    }
    case "route-gap":
      return {
        ...nothing,
        params: { point: naming.point(at(0)) },
        share: true,
      };
    case "required-hidden": {
      const section = finding.elements[0]?.section;
      return {
        key: `${finding.rule_id}.${section === "forms" ? "form" : section === "meta" ? "meta" : "other"}`,
        params: {},
      };
    }
    case "field-never-visible":
      return { ...nothing, params: {} };
    case "variant-lang-outside-langs": {
      const langs = listAfter(message, /называет\s+(.+?),\s+а\s/)
        .map((code) => naming.language(code))
        .join(", ");
      const doc = finding.elements[0]?.id ?? "";
      return {
        key: `${finding.rule_id}.${langs === "" ? "plain" : "langs"}`,
        params: { document: naming.document(doc), langs },
      };
    }
    case "skip-if-nda-without-nda":
      return {
        ...nothing,
        params: {
          document: naming.document(at(0)),
          point: naming.point(at(1)),
        },
      };
    case "when-unknown-person":
      return {
        key: `${finding.rule_id}.${
          pointerEnds(finding, "/slot_id")
            ? "slot"
            : pointerEnds(finding, "/doc_id")
              ? "document"
              : "person"
        }`,
        params: {},
      };
    case "when-never-held":
    case "when-always-held":
      return {
        ...nothing,
        params: {
          signature: naming.slot(at(0)),
          document: naming.document(at(1)),
          point: naming.point(at(2)),
        },
      };
    case "slot-when-overlap":
      return {
        ...nothing,
        params: {
          point: naming.point(at(0)),
          signature: naming.slot(at(1)),
          document: naming.document(at(2)),
        },
      };
    case "document-never-active":
      return { ...nothing, params: { document: naming.document(at(0)) } };
    case "item-never-active":
      return {
        ...nothing,
        params: {
          document: naming.document(at(0)),
          point: naming.point(at(1)),
        },
      };
    case "point-empty": {
      const all = message.includes("во всех комбинациях");
      const n = /в\s+(\d+)\s+комбинациях/.exec(message)?.[1];
      const total = /из\s+(\d+)\s+строк/.exec(message)?.[1];
      return {
        key: `${finding.rule_id}.${all || !n || !total ? "all" : "some"}`,
        params: {
          point: naming.point(at(0)),
          n: n ?? "",
          total: total ?? "",
        },
      };
    }
    case "translation-missing": {
      const langs = listAfter(
        message,
        /нет перевода .+? на\s+([a-z, ]+?)\s*\(языки/,
      )
        .map((code) => naming.language(code))
        .join(", ");
      const kind = pointerEnds(finding, "/help") ? "hint" : "name";
      return {
        key: `${finding.rule_id}.${kind}`,
        params: { langs: langs === "" ? t("plain.fallback.lang") : langs },
      };
    }
    case "builtin-gate-mismatch": {
      const variant = pointerEnds(finding, "/options")
        ? "manualsOptions"
        : message.startsWith("Документ «nda»")
          ? "ndaDocument"
          : message.startsWith("Поле проекта nda")
            ? "ndaField"
            : "manualsField";
      return { key: `${finding.rule_id}.${variant}`, params: {} };
    }
    case "dimension-no-effect":
      return { ...nothing, params: { condition: naming.input(at(0)) } };
    case "jinja-fail-open":
    case "jinja-unknown-meta-key": {
      const doc = fileDocument(finding.file);
      return {
        ...nothing,
        params: {
          document:
            doc === null ? t("plain.fallback.document") : naming.document(doc),
        },
      };
    }
    case "atlas-skipped": {
      const rows = /\((\d+)\s+строк/.exec(message)?.[1];
      const limit = /предела\s+(\d+)/.exec(message)?.[1];
      return {
        key: `${finding.rule_id}.${rows && limit ? "numbers" : "plain"}`,
        params: { rows: rows ?? "", limit: limit ?? "" },
      };
    }
    default:
      return nothing;
  }
};

/** Что пойдёт под «Технические подробности»: идентификатор правила, место и сырой текст сервера. */
const techOf = (
  finding: OutcomeFinding,
  t: TFunction,
): { label: string; value: string }[] => {
  const rows: { label: string; value: string | null }[] = [
    { label: t("plain.tech.rule"), value: finding.rule_id },
    { label: t("plain.tech.file"), value: finding.file },
    { label: t("plain.tech.pointer"), value: finding.pointer },
    { label: t("plain.tech.message"), value: finding.message },
    { label: t("plain.tech.hint"), value: finding.hint ?? null },
  ];
  return rows.flatMap((row) =>
    row.value === null || row.value === ""
      ? []
      : [{ label: row.label, value: row.value }],
  );
};

export const plainFinding = (
  finding: OutcomeFinding,
  naming: Naming,
  t: TFunction,
): PlainFinding => {
  const tech = techOf(finding, t);
  if (!isLintRule(finding.rule_id)) {
    return {
      title: finding.message,
      how: finding.hint ?? t("plain.finding.unknown.how"),
      extra: null,
      known: false,
      tech,
    };
  }
  const { key, params, share } = partsOf(finding, naming, t);
  const counts = shareOf(finding.message);
  return {
    title: t(`plain.finding.${key}.title`, params),
    how: t(`plain.finding.${key}.how`, params),
    extra:
      share && counts
        ? t("plain.finding.share", { n: counts.n, total: counts.total })
        : null,
    known: true,
    tech,
  };
};
