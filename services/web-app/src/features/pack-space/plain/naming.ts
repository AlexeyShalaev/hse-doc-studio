import type { TFunction } from "i18next";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

// Названия для людей (pack-studio-ux.md, принцип P5 и раздел 6): роли, подписи, документы, точки сдачи
// и условия называются так, как их называет сам пак или словарь, а не идентификаторами. Чистая
// функция над тем, что версия уже отдаёт клиенту; чего нет, получает нейтральное слово
// («один из документов»), а сам идентификатор остаётся только в «Технических подробностях».

type Localized = Partial<Record<string, string>>;

export type NamingSource = {
  lng: string;
  t: TFunction;
  documents?: readonly { id: string; name: Localized }[] | undefined;
  slots?: readonly { id: string; label: Localized }[] | undefined;
  points?: readonly { id: string | null; name: Localized | null }[] | undefined;
  /** Название условия экрана или `null`, если версия его не знает. */
  inputLabel?: ((id: string) => string | null) | undefined;
};

export type Naming = {
  /** Роль участника: «Научный руководитель», «Автор 2». */
  role: (id: string) => string;
  /** Подпись из списка подписей версии. */
  slot: (id: string) => string;
  document: (id: string) => string;
  /** Точка сдачи («Заявление на тему»). */
  point: (id: string) => string;
  /** Название условия экрана. */
  input: (id: string) => string;
  /** Язык: «русский», «английский»; незнакомый код большими буквами. */
  language: (code: string) => string;
  /** Часть результата словами: документ, подпись, участник. Идентификатор наружу не выходит. */
  element: (section: string, id: string) => string;
};

const AUTHOR_N = /^author(\d+)$/;

export const makeNaming = (source: NamingSource): Naming => {
  const { lng, t } = source;
  const own = (key: string): string | null => {
    const text = t(key, { defaultValue: "" });
    return text === "" ? null : text;
  };
  const fallback = (kind: string): string => t(`plain.fallback.${kind}`);

  const role = (id: string): string => {
    const n = AUTHOR_N.exec(id)?.[1];
    if (n) return t("plain.role.authorN", { n });
    const fromPack = source.slots?.find((slot) => slot.id === id);
    if (fromPack) return pickLocalized(fromPack.label, lng, fallback("role"));
    return own(`plain.role.${id}`) ?? fallback("role");
  };
  const slot = (id: string): string => {
    const fromPack = source.slots?.find((item) => item.id === id);
    if (fromPack) return pickLocalized(fromPack.label, lng, fallback("slot"));
    return AUTHOR_N.test(id) || own(`plain.role.${id}`) !== null
      ? role(id)
      : fallback("slot");
  };
  const document = (id: string): string => {
    const found = source.documents?.find((item) => item.id === id);
    return found
      ? pickLocalized(found.name, lng, fallback("document"))
      : fallback("document");
  };
  const point = (id: string): string => {
    const found = source.points?.find((item) => item.id === id);
    return found
      ? pickLocalized(found.name ?? undefined, lng, fallback("point"))
      : fallback("point");
  };
  const input = (id: string): string =>
    source.inputLabel?.(id) ?? fallback("input");
  const language = (code: string): string =>
    own(`plain.lang.${code}`) ?? code.toUpperCase();

  const element = (section: string, id: string): string => {
    const [first = "", second = "", third = ""] = id.split("/");
    switch (section) {
      case "documents":
        return document(id);
      case "participants":
        return role(id);
      case "points":
        return second === ""
          ? point(first)
          : t("plain.element.item", {
              point: point(first),
              document: document(second),
            });
      case "route":
        return third === ""
          ? t("plain.element.route", { point: point(first) })
          : t("plain.element.signature", {
              signature: slot(third),
              document: document(second),
              point: point(first),
            });
      case "meta":
        return source.inputLabel?.(`meta.${id}`) ?? fallback("metaField");
      case "forms":
        return second === "" ? fallback("form") : fallback("formField");
      default:
        return fallback("check");
    }
  };
  return { role, slot, document, point, input, language, element };
};
