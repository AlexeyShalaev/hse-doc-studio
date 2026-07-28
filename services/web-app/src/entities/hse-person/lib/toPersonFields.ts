import type { HsePersonDetail } from "../api";

export type HsePersonFields = {
  name: string;
  title: string;
  degree: string;
};

/**
 * Maps an HSE profile to the person fields our supervisor/employee cards edit.
 * The должность line reads «Должность, Подразделение» (e.g. «Доцент, Департамент
 * программной инженерии»); the учёная степень fills the separate degree field.
 */
export const toPersonFields = (detail: HsePersonDetail): HsePersonFields => ({
  name: detail.full_name,
  title: [detail.position, detail.department].filter(Boolean).join(", "),
  degree: detail.degree,
});
