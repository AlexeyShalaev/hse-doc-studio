import { createContext, useContext } from "react";
import { useNavigate } from "react-router";
import type { OutcomeInput, OutcomeRuleRef } from "@entities/pack-studio";
import { packOutcomePath, packRulePath } from "@entities/pack-studio";
import {
  ruleLocation,
  type RuleLocation,
} from "@entities/pack-studio/outcome/rules";
import { writeOutcomeSearch } from "@entities/pack-studio/outcome/urlState";
import { OutcomeModelContext } from "@entities/pack-studio/outcome/model";

/**
 * Что нужно списку изменений для «Почему?»: словарь вводных версии, телефон и переход к правилу.
 * Экран «Результат» даёт это из своей модели; блок «Что изменится» в «Предложить изменения»
 * живёт вне экрана и подставляет своё (`ChangeEnvContext`).
 */
export type ChangeEnv = {
  inputs: readonly OutcomeInput[] | undefined;
  phone: boolean;
  locate: (rule: OutcomeRuleRef) => RuleLocation | null;
  /** Открыть правило в режиме «Файлы»; `null`: перехода нет (кнопки не показываются). */
  open: ((rule: OutcomeRuleRef) => void) | null;
};

export const ChangeEnvContext = createContext<ChangeEnv | null>(null);

/** Окружение списка изменений: подставленное блоком либо из модели экрана «Результат». */
export const useChangeEnv = (): ChangeEnv => {
  const injected = useContext(ChangeEnvContext);
  const model = useContext(OutcomeModelContext);
  const navigate = useNavigate();
  if (injected) return injected;
  if (!model) throw new Error("ChangeEnvContext is missing");
  const { workspaceId, ref, versionPath, url } = model;
  const back = packOutcomePath(
    workspaceId,
    ref,
    writeOutcomeSearch(new URLSearchParams(), url.state).toString(),
  );
  return {
    inputs: model.inputs.data?.inputs,
    phone: model.phone,
    locate: (rule) => ruleLocation(versionPath, rule),
    open: (rule) => {
      const where = ruleLocation(versionPath, rule);
      if (!where) return;
      void navigate(
        packRulePath(workspaceId, where.file, {
          pointer: where.pointer,
          pane: where.form ? "form" : "source",
          from: back,
        }),
      );
    },
  };
};
