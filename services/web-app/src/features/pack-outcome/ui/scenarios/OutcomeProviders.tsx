import type { ReactNode } from "react";
import { OutcomeModelContext, type OutcomeModel } from "../../model";
import type { ScenarioDialog } from "./context";
import { RuleEditHost } from "../edit/RuleEditHost";
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

/** Модель экрана, сценарии, правка по месту и предпросмотр PDF над ней: контексты одним узлом, чтобы разметка экрана не сдвигалась. */
export const OutcomeProviders = ({
  model,
  scenarioDialog,
  previewDocument = null,
  children,
}: OutcomeProvidersProps) => (
  <OutcomeModelContext.Provider value={model}>
    <ScenariosHost initialDialog={scenarioDialog}>
      <RuleEditHost>
        <PreviewHost initialDocument={previewDocument}>{children}</PreviewHost>
      </RuleEditHost>
    </ScenariosHost>
  </OutcomeModelContext.Provider>
);
