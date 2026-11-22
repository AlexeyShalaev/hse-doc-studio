import { useMemo } from "react";
import {
  usePackOutcomeInputs,
  type OutcomeElementRef,
} from "@entities/pack-studio";
import { useLabeler } from "@features/pack-outcome/check";
import { useSpace } from "../context/SpaceContext";
import { useSituation } from "../context/useSituation";
import { useSpaceNav } from "../context/useSpaceNav";
import { useNaming } from "../plain/useNaming";
import { filePathIn, witnessInputs } from "./lib";

/**
 * Общее для частей «Проверки»: условия версии и подписи к ним, переходы на «Результат» и в
 * «Содержимое». Расчёт здесь всегда по моим текущим правкам (`work_tree`): выбора состояния в
 * новом интерфейсе нет.
 */
export const useCheckEnv = () => {
  const { workspace, versionRef, version, released } = useSpace();
  const nav = useSpaceNav();
  const situation = useSituation();
  const inputs = usePackOutcomeInputs(workspace.id, versionRef, "work_tree");
  const labeler = useLabeler(inputs.data?.inputs);
  const naming = useNaming(workspace.id, versionRef, inputs.data?.inputs);
  const versionPath = version?.path ?? "";
  const { inputs: current, caseId } = situation;
  const known = inputs.data?.inputs;

  return useMemo(
    () => ({
      workspaceId: workspace.id,
      ref: versionRef,
      versionPath,
      released,
      inputs,
      labeler,
      /** Названия документов, подписей и участников словами пака. */
      naming,
      /** Результат при условиях из находки или правила (поверх нынешних условий экрана). */
      showSituation: (witness: Readonly<Record<string, string>>) => {
        nav.go({
          tab: "result",
          inputs: witnessInputs(known, current, caseId, witness),
        });
      },
      /** Результат с выбранным элементом. */
      showElement: (element: OutcomeElementRef) => {
        nav.go({ tab: "result", sel: `${element.section}:${element.id}` });
      },
      /** Готовый случай как условия экрана. */
      showCase: (id: string) => {
        nav.go({ tab: "result", case: id, inputs: {} });
      },
      /** Файл версии (путь от каталога версии) в «Содержимом»; `false`, если файл вне версии. */
      openFile: (file: string, pointer: string | null): boolean => {
        const path = filePathIn(versionPath, file);
        if (path === null) return false;
        nav.go({
          tab: "content",
          file: path,
          extra: { at: pointer, from: nav.href() },
        });
        return true;
      },
    }),
    [
      workspace.id,
      versionRef,
      versionPath,
      released,
      inputs,
      labeler,
      naming,
      nav,
      known,
      current,
      caseId,
    ],
  );
};

export type CheckEnv = ReturnType<typeof useCheckEnv>;
