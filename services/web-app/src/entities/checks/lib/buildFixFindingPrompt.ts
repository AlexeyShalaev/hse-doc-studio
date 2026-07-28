import { i18n } from "@shared/lib";

export type FixFindingParams = {
  docCode: string;
  docId: string;
  ruleId: string;
  message: string;
  file: string | undefined;
  line: number | undefined;
};

const location = (
  file: string | undefined,
  line: number | undefined,
): string =>
  file
    ? i18n.t("entitiesMisc:fixFinding.location", {
        file,
        lineSuffix: line != null ? `:${String(line)}` : "",
      })
    : "";

/**
 * Agent prompt asking the AI to fix a single check finding. Shared by the
 * «Проверки» tab and the editor's inline finding menu so both phrase the
 * request identically.
 */
export const buildFixFindingPrompt = (params: FixFindingParams): string =>
  i18n.t("entitiesMisc:fixFinding.prompt", {
    docCode: params.docCode,
    docId: params.docId,
    ruleId: params.ruleId,
    message: params.message,
    location: location(params.file, params.line),
  });
