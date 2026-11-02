import { useTranslation } from "react-i18next";

/** Подпись действия журнала на языке интерфейса; неизвестный код остаётся как есть. */
export const useAuditActionLabel = (): ((action: string) => string) => {
  const { t, i18n } = useTranslation("adminAudit");
  return (action) => {
    const key = "audit.actions." + action.replaceAll(".", "_");
    return i18n.exists(key, { ns: "adminAudit" }) ? t(key) : action;
  };
};
