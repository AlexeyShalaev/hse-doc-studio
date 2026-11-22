import { useMemo, type ReactNode } from "react";
import { useIsPhoneWidth } from "@shared/lib";
import { useTranslation } from "react-i18next";
import { ChangeEnvContext, type ChangeEnv } from "./compare/changeEnv";
import { ChangeWordsContext, type ChangeWords } from "./compare/changeWords";
import { ruleLocation } from "@entities/pack-studio/outcome/rules";
import { plainChange } from "../plain/changes";
import type { CheckEnv } from "./useCheckEnv";

/**
 * Окружение прежнего списка изменений («Почему?»): подписи условий версии и переход к месту
 * правила в «Содержимом» нового интерфейса вместо старого экрана файлов.
 */
export const CheckChangeEnv = ({
  env,
  children,
}: {
  env: CheckEnv;
  children: ReactNode;
}) => {
  const phone = useIsPhoneWidth();
  const { t } = useTranslation("packSpace");
  const { naming } = env;
  const words = useMemo<ChangeWords>(
    () => ({
      words: (change) => plainChange(change, naming, t),
      techSummary: t("plain.tech.summary"),
    }),
    [naming, t],
  );
  const known = env.inputs.data?.inputs;
  const { versionPath, openFile } = env;
  const value = useMemo<ChangeEnv>(
    () => ({
      inputs: known,
      phone,
      locate: (rule) => ruleLocation(versionPath, rule),
      open: (rule) => {
        if (rule.origin === "manifest" && rule.file !== null) {
          openFile(rule.file, rule.pointer);
        }
      },
    }),
    [known, phone, versionPath, openFile],
  );
  return (
    <ChangeEnvContext.Provider value={value}>
      <ChangeWordsContext.Provider value={words}>
        {children}
      </ChangeWordsContext.Provider>
    </ChangeEnvContext.Provider>
  );
};
