import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { DurationUnits } from "./format";

export const useDurationUnits = (): DurationUnits => {
  const { t } = useTranslation("adminOps");
  return useMemo(
    () => ({ s: t("units.s"), min: t("units.min"), h: t("units.h") }),
    [t],
  );
};
