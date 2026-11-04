import type { TFunction } from "i18next";
import {
  deviceKind,
  type PersonOnline,
  type PeopleActivity,
} from "@entities/connected-device";

/** «редактирует «Заявка»», «смотрит замечания», «работает локально»: место человека словами. */
export const whereText = (
  t: TFunction,
  activity: PeopleActivity,
  docName: string | null,
): string =>
  docName !== null && activity !== "local" && activity !== "browsing"
    ? t(`people.whereDoc.${activity}`, { doc: docName })
    : t(`people.where.${activity}`);

/** С чего работает человек: только веб или локальная Студия, без деталей машины. */
export const deviceText = (t: TFunction, person: PersonOnline): string =>
  t(`people.device.${deviceKind(person)}`);

export type PersonLabelParts = {
  name: string;
  role: string;
  where: string;
  device: string;
};

/** Полная подпись для скринридера и подсказки. */
export const personSummary = (
  t: TFunction,
  person: PersonOnline,
  parts: PersonLabelParts,
): string =>
  t("people.summary", {
    name: person.me ? t("people.you", { name: parts.name }) : parts.name,
    role: parts.role,
    where: parts.where,
    device: parts.device,
  });
