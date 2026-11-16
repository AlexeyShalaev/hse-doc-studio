import type { ReactNode } from "react";
import { OutcomeModelContext, type OutcomeModel } from "../../model";
import type { ScenarioDialog } from "./context";
import { ScenariosHost } from "./ScenariosHost";

type OutcomeProvidersProps = {
  model: OutcomeModel;
  /** Окно сценариев, открытое сразу (галерея состояний). */
  scenarioDialog: ScenarioDialog | null;
  children: ReactNode;
};

/** Модель экрана и сценарии над ней: оба контекста одним узлом, чтобы разметка экрана не сдвигалась. */
export const OutcomeProviders = ({
  model,
  scenarioDialog,
  children,
}: OutcomeProvidersProps) => (
  <OutcomeModelContext.Provider value={model}>
    <ScenariosHost initialDialog={scenarioDialog}>{children}</ScenariosHost>
  </OutcomeModelContext.Provider>
);
