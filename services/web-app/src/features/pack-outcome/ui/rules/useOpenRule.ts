import { useNavigate } from "react-router";
import {
  packFormKind,
  packOutcomePath,
  packRulePath,
  type OutcomeRuleRef,
  type RulePane,
} from "@entities/pack-studio";
import { ruleLocation } from "../../lib/rules";
import { writeOutcomeSearch } from "../../lib/urlState";
import { useOutcomeModel } from "../../model";

/**
 * «Открыть правило» и «Исходник»: режим «Файлы» на файле правила, указатель и вкладка в адресе.
 * Адрес возврата несёт всё состояние экрана (вводные, сценарий, выбранный элемент), поэтому
 * «Назад к результату» открывает тот же результат на том же элементе.
 */
export const useOpenRule = () => {
  const navigate = useNavigate();
  const { workspaceId, ref, versionPath, url } = useOutcomeModel();
  const back = packOutcomePath(
    workspaceId,
    ref,
    writeOutcomeSearch(new URLSearchParams(), url.state).toString(),
  );
  return {
    /** Место правила и вкладка по умолчанию (форма, если файл её имеет). */
    locate: (rule: OutcomeRuleRef) => ruleLocation(versionPath, rule),
    /**
     * Место находки линтера: файл от каталога версии и указатель из ответа сервера. Файл вне
     * каталога версии (`..`, абсолютный путь) не открывается: возвращает `false`.
     */
    openPlace: (file: string, pointer: string | null): boolean => {
      if (
        versionPath === "" ||
        file === "" ||
        file.startsWith("/") ||
        file.split("/").includes("..")
      ) {
        return false;
      }
      const path = `${versionPath}/${file}`;
      void navigate(
        packRulePath(workspaceId, path, {
          pointer,
          pane:
            pointer !== null && packFormKind(path) !== null ? "form" : "source",
          from: back,
        }),
      );
      return true;
    },
    open: (rule: OutcomeRuleRef, pane?: RulePane) => {
      const where = ruleLocation(versionPath, rule);
      if (!where) return;
      void navigate(
        packRulePath(workspaceId, where.file, {
          pointer: where.pointer,
          pane: pane ?? (where.form ? "form" : "source"),
          from: back,
        }),
      );
    },
  };
};
