import { usePackOutcome, type PackOutcome } from "@entities/pack-studio";
import { useOutcomeModel } from "../../model";

/**
 * Результат сценария для готовых утверждений: у нового сценария это результат экрана, у
 * существующего свой расчёт по его вводным (запрос общий с экраном, когда выбран он же).
 */
export const useScenarioOutcome = (
  scenario: string | null,
  fallback: PackOutcome | undefined,
): PackOutcome | undefined => {
  const { workspaceId, ref, url } = useOutcomeModel();
  const own = usePackOutcome(
    workspaceId,
    ref,
    { state: url.state.state, scenario },
    scenario !== null,
  );
  return scenario === null ? fallback : own.data;
};
