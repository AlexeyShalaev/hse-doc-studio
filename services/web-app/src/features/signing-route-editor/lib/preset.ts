import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type {
  PresetCondition,
  RoutePreset,
  RouteSlotRef,
} from "@entities/signing-route";

// Маршрут из шаблона (docs/design/signing-route.md, 15.7): условие слота сверх точки переводится по
// коду (персона и роль), а не берётся из пака: текста условия у пака нет.

const PERSONS = new Set(["supervisor", "co_supervisor", "academic_supervisor"]);

/** Условие словами: «научный руководитель не из ВШЭ», «указан консультант». */
export const useConditionText = () => {
  const { t } = useTranslation("signingRouteEditor");
  return useCallback(
    (when: PresetCondition): string => {
      if (!PERSONS.has(when.person)) return t("condition.other");
      return when.role === null
        ? t(`condition.${when.person}`)
        : t(`condition.${when.person}_${when.role}`);
    },
    [t],
  );
};

const same = (a: RouteSlotRef, b: RouteSlotRef): boolean =>
  a.doc_id === b.doc_id && a.slot_id === b.slot_id;

/** Условие, по которому шаблон добавил слот сверх точки; null без условия или без пресета. */
export const presetConditionOf = (
  preset: RoutePreset | null,
  pair: RouteSlotRef,
): PresetCondition | null =>
  preset?.extra_slots.find((slot) => same(slot, pair))?.when ?? null;

/** Условие слота, который шаблон не добавил: подсказка в «Добавить подпись …». */
export const skippedConditionOf = (
  preset: RoutePreset | null,
  pair: RouteSlotRef,
): PresetCondition | null =>
  preset?.skipped_by_condition.find((slot) => same(slot, pair))?.when ?? null;
