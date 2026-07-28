import { i18n } from "@shared/lib";
import type { RequirementFormat } from "../api/requirementsApi";

const KIND_LABEL_KEY: Record<RequirementFormat["kind"], string> = {
  macro: "entitiesMisc:requirementsFormat.kindMacro",
  id: "entitiesMisc:requirementsFormat.kindId",
  custom: "entitiesMisc:requirementsFormat.kindCustom",
};

/**
 * Agent prompt asking the AI to help configure the requirements-traceability
 * format (macro / id_pattern / custom regex). Steers it through the new
 * preview_requirements_format → set_requirements_format flow so the «ИИ» button
 * in the format editor and any other caller phrase the request identically.
 */
export const buildRequirementsFormatPrompt = (
  currentKind: RequirementFormat["kind"],
): string =>
  i18n.t("entitiesMisc:requirementsFormat.prompt", {
    kindLabel: i18n.t(KIND_LABEL_KEY[currentKind]),
  });
