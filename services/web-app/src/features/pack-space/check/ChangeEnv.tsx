import { useMemo, type ReactNode } from "react";
import { useIsPhoneWidth } from "@shared/lib";
import {
  ChangeEnvContext,
  ruleLocation,
  type ChangeEnv,
} from "@features/pack-outcome/check";
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
      {children}
    </ChangeEnvContext.Provider>
  );
};
