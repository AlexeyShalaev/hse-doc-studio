import type { ReactNode } from "react";
import { OutcomeModelContext, type OutcomeModel } from "../../model";
import type { ScenarioDialog } from "./context";
import { PreviewHost } from "../preview/PreviewHost";
import { ScenariosHost } from "./ScenariosHost";

type OutcomeProvidersProps = {
  model: OutcomeModel;
  /** Окно сценариев, открытое сразу (галерея состояний). */
  scenarioDialog: ScenarioDialog | null;
  /** Документ, чей предпросмотр открыт сразу (галерея состояний). */
  previewDocument?: string | null;
  children: ReactNode;
};

/** Модель экрана и сценарии над ней: оба контекста одним узлом, чтобы разметка экрана не сдвигалась. */
export const OutcomeProviders = ({
  model,
  scenarioDialog,
  previewDocument = null,
  children,
}: OutcomeProvidersProps) => (
  <OutcomeModelContext.Provider value={model}>
    <ScenariosHost initialDialog={scenarioDialog}>
      <PreviewHost initialDocument={previewDocument}>{children}</PreviewHost>
    </ScenariosHost>
  </OutcomeModelContext.Provider>
);
