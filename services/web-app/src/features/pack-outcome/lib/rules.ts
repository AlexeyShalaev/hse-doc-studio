import {
  packFormKind,
  type OutcomeRuleRef,
  type OutcomeTrace,
} from "@entities/pack-studio";

// Правило из ответа сервера: где оно записано (файл и указатель) и как к нему перейти. Клиент
// ничего не решает: файл и указатель приходят готовыми (R14), здесь они лишь склеиваются с
// каталогом версии и проверяются на «форму есть».

export type RuleLocation = {
  /** Файл от папки паков (`hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml`). */
  file: string;
  /** JSON Pointer записи внутри файла. */
  pointer: string;
  /** У файла есть вкладка «Форма» (version.yaml, doc.yaml, файлы проверок). */
  form: boolean;
};

/** Где лежит правило манифеста; зашитые в движок правила места не имеют (null). */
export const ruleLocation = (
  versionPath: string,
  rule: OutcomeRuleRef,
): RuleLocation | null => {
  if (rule.origin !== "manifest" || rule.file === null) return null;
  if (rule.pointer === null || versionPath === "") return null;
  const file = `${versionPath}/${rule.file}`;
  return { file, pointer: rule.pointer, form: packFormKind(file) !== null };
};

/** Ключ места правила: одинаковые правила разных решений склеиваются в списках. */
export const ruleKey = (rule: OutcomeRuleRef): string =>
  rule.origin === "manifest"
    ? `${rule.file ?? ""}#${rule.pointer ?? ""}`
    : `builtin:${rule.builtin ?? ""}`;

/** Предмет условия относится к вводной: сама (`meta.nda`) или её свойство (`supervisor.role`). */
export const readsInput = (trace: OutcomeTrace, input: string): boolean =>
  trace.terms.some(
    (term) => term.subject === input || term.subject.startsWith(`${input}.`),
  );
