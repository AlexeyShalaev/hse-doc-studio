import type { PackVersionState, UpdateClass } from "@entities/pack-studio";
import { ApiError } from "@shared/api";

// Номер версии подбирается сам (pack-studio-ux.md, 5.6, раздел 10 про «Править копию»): копия
// создаётся небольшой правкой (patch), а правки человека могут требовать больше (minor, major).
// Тогда Студия берёт номер нужного класса из отчёта версии и меняет его при отправке, а человеку
// говорит одну фразу вместо ошибки проверки. Чистые функции без React.

/** Какой номер нужен правкам и почему. */
export type NumberFix = {
  /** Номер версии, на который перейдёт копия. */
  to: string;
  /** Класс номера (по минимуму, который требуют правки). */
  cls: UpdateClass;
  /** Код причины классификатора (`document_scope`, `field_added`, ...); `null`: причин не названо. */
  cause: string | null;
};

/**
 * Нужна ли смена номера: версия не выпущена, её номер мягче того, что требуют правки, и в отчёте
 * есть свободный номер нужного класса. Иначе `null`: номер подходит или менять его нечем.
 */
export const resolveNumberFix = (
  state: PackVersionState | null,
): NumberFix | null => {
  if (!state || state.released || state.number_ok || state.minimum === null) {
    return null;
  }
  const to = state.numbers[state.minimum];
  if (!to || to === state.version.version) return null;
  // Причина: первая из тех, что требуют этот самый класс (а не более мягкого).
  const reason = state.reasons.find((item) => item.minimum === state.minimum);
  return { to, cls: state.minimum, cause: reason?.code ?? null };
};

/** Какую группу слов брать для причины: ключ `changes.submit.number.cause.<group>`. */
const CAUSE_GROUP: Record<string, string> = {
  document_scope: "documents",
  document_added: "newDocuments",
  version_scope: "scope",
  field_added: "fields",
  optional_field_added: "fields",
  field_type: "fields",
  group_added: "fields",
  form_added: "forms",
  profile_added: "checkpoints",
  item_added: "checkpoints",
  item_removed: "checkpoints",
  extra_items: "checkpoints",
  methods: "checkpoints",
  slot_added: "signatures",
  slot_scope: "signatures",
  slot_required: "signatures",
  item_signatures: "signatures",
  variant_added: "variants",
  check_rule_added: "checks",
  check_file_added: "checks",
};

/** Группа слов для причины; `null`: общая фраза без причины. */
export const causeGroup = (fix: NumberFix): string | null =>
  fix.cls === "major"
    ? "regulation"
    : fix.cause
      ? (CAUSE_GROUP[fix.cause] ?? null)
      : null;

/** Отказ сервера про номер: его можно исправить сменой номера. */
export const isNumberError = (error: unknown): boolean =>
  error instanceof ApiError &&
  (error.code === "class_softer_than_changes" ||
    error.code === "version_number_invalid");
