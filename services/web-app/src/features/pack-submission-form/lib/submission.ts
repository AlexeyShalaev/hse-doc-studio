import type {
  PackSubmission,
  PackSubmissionItem,
  PackSubmissionProfile,
  PackSubmissionWhen,
} from "@entities/pack-studio";

// Чистые помощники формы точек сдачи (template-studio.md, 5.5-5.8, срез T13). Сервер
// проверяет правку строгим разбором лоадера и схемой; здесь только то, что форма
// показывает до отправки: какие слоты применимы, условия `when`, подсказка срока.

export const LANGS = ["ru", "en"] as const;

export const SIGN_METHODS = ["image", "detached", "pades"] as const;
export type SignMethod = (typeof SIGN_METHODS)[number];

export const WHEN_PERSONS = [
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
] as const;
export const WHEN_ROLES = ["university", "company"] as const;

/** Закрытый список условий `when` (signing-route.md, 15.3): «всегда» и персона с ролью или без. */
export const WHEN_KEYS: readonly string[] = [
  "always",
  ...WHEN_PERSONS.flatMap((person) => [
    person,
    ...WHEN_ROLES.map((role) => `${person}:${role}`),
  ]),
];

export const whenKey = (when: PackSubmissionWhen | null): string =>
  when === null
    ? "always"
    : when.role
      ? `${when.person}:${when.role}`
      : when.person;

export const whenFromKey = (key: string): PackSubmissionWhen | null => {
  if (key === "always") return null;
  const [person = "", role] = key.split(":");
  const known = (WHEN_PERSONS as readonly string[]).includes(person);
  if (!known) return null;
  return {
    person: person as PackSubmissionWhen["person"],
    role: role === "university" || role === "company" ? role : null,
  };
};

export type SlotInfo = PackSubmission["slots"][number];

/** Слоты каталога, применимые к документу (`applies_to`), в порядке каталога. */
export const slotsFor = (data: PackSubmission, docId: string): SlotInfo[] =>
  data.slots.filter((slot) => slot.applies_to.includes(docId));

/** Документы пунктов профиля (без битых записей), в порядке пунктов. */
export const profileDocs = (profile: PackSubmissionProfile): string[] => [
  ...new Set(
    profile.items.flatMap((item) => (item.entry ? [item.entry.doc_id] : [])),
  ),
];

/** Подписи точки по документу: слот сверх них это «слот сверх точки» (у него бывает `when`). */
export const pointSlots = (
  profile: PackSubmissionProfile,
  docId: string,
): Set<string> =>
  new Set(
    profile.items.flatMap((item) =>
      item.entry?.doc_id === docId ? item.entry.signatures : [],
    ),
  );

/** Пункт после переключения подписи: способы слота уходят вместе с ним. */
export const toggleSignature = (
  item: PackSubmissionItem,
  slot: string,
  on: boolean,
): PackSubmissionItem => {
  const signatures = on
    ? [...item.signatures.filter((s) => s !== slot), slot]
    : item.signatures.filter((s) => s !== slot);
  const methods = Object.fromEntries(
    Object.entries(item.methods).filter(([key]) => signatures.includes(key)),
  );
  return { ...item, signatures, methods };
};

/** Пункт после переключения способа слота; пустой список значит «любой способ». */
export const toggleMethod = (
  item: PackSubmissionItem,
  slot: string,
  method: SignMethod,
  on: boolean,
): PackSubmissionItem => {
  const current = item.methods[slot] ?? [];
  const next = SIGN_METHODS.filter((m) =>
    m === method ? on : current.includes(m),
  );
  const others = Object.entries(item.methods).filter(([key]) => key !== slot);
  const methods = Object.fromEntries(
    next.length === 0 ? others : [...others, [slot, [...next]]],
  );
  return { ...item, methods };
};

export const KINDS = ["research", "project"] as const;
export type KindsKey = "both" | (typeof KINDS)[number];

export const kindsKey = (kinds: readonly string[]): KindsKey =>
  kinds.length === 1 && (kinds[0] === "research" || kinds[0] === "project")
    ? kinds[0]
    : "both";

export const kindsOf = (key: string): ("research" | "project")[] =>
  key === "research" || key === "project" ? [key] : [];

// Конкретные даты в подсказке срока: те же правила, что у сервера (core/checkpoint_deadlines.py).
const MONTHS_RU =
  "(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)";
const MONTHS_EN =
  "(January|February|March|April|May|June|July|August|September|October|November|December)";
const DATE_PATTERNS: readonly RegExp[] = [
  new RegExp(`(^|[^\\p{L}\\p{N}_])\\d{1,2}\\s+${MONTHS_RU}`, "iu"),
  /(?<![\d.])\d{1,2}\.\d{1,2}(?:\.\d{2,4})?(?!\.?\d)/u,
  /\b\d{4}-\d{2}-\d{2}\b/u,
  new RegExp(`\\b${MONTHS_EN}\\s+\\d{1,2}\\b`, "i"),
  new RegExp(`\\b\\d{1,2}(st|nd|rd|th)?\\s+${MONTHS_EN}\\b`, "i"),
];

export const HINT_MAX = 200;

export const hasDate = (text: string): boolean =>
  DATE_PATTERNS.some((pattern) => pattern.test(text));

export type HintIssue = "missing" | "long" | "date";

/** Что не так с подсказкой срока одного языка; null, если годится. */
export const hintIssue = (text: string): HintIssue | null => {
  const trimmed = text.trim();
  if (!trimmed) return "missing";
  if (trimmed.length > HINT_MAX) return "long";
  return hasDate(trimmed) ? "date" : null;
};

/**
 * Находки проверок про профиль: линтер пишет «профиль <id>: ...», схема даёт указатель
 * `/pack_submission/profiles/<индекс>/...`.
 */
export const profileFindings = <
  T extends { message: string; pointer: string | null },
>(
  findings: readonly T[],
  profile: { id: string | null; index: number },
): T[] => {
  const pointer = `/pack_submission/profiles/${String(profile.index)}`;
  return findings.filter(
    (f) =>
      (profile.id !== null && f.message.includes(`профиль ${profile.id}:`)) ||
      f.pointer === pointer ||
      (f.pointer?.startsWith(`${pointer}/`) ?? false),
  );
};
