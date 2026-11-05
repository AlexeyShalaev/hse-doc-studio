import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { reloadToNewBuild, useStaleBuildStore } from "@shared/lib";

/**
 * Ненавязчивая плашка внизу окна: вышла новая версия Студии, а вкладка открыта на старой. Ничего не
 * перезагружает сама, чтобы не потерять ввод; экран ошибки сборки показывает то же сообщение сам.
 */
export const StaleBuildBanner = () => {
  const { t } = useTranslation("appChrome");
  const reason = useStaleBuildStore((state) => state.reason);
  const screenShown = useStaleBuildStore((state) => state.screenShown);
  if (reason === null || screenShown) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="stale-build-banner"
      style={{
        position: "fixed",
        left: "0.75rem",
        right: "0.75rem",
        bottom: "calc(0.75rem + env(safe-area-inset-bottom, 0rem))",
        zIndex: 80,
        margin: "0 auto",
        maxWidth: "34rem",
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "0.5rem 0.75rem",
        padding: "0.5rem 0.75rem",
        border: "1px solid var(--c-info)",
        borderRadius: "var(--r-3)",
        background: "var(--bg-1)",
        color: "var(--fg-0)",
        boxShadow: "var(--shadow-1)",
        fontSize: "0.8125rem",
      }}
    >
      <span style={{ flex: "1 1 14rem", minWidth: 0, lineHeight: 1.4 }}>
        {t("staleBuild.banner")}
      </span>
      <button
        type="button"
        className="btn xs"
        data-testid="stale-build-refresh"
        style={{ flexShrink: 0, minHeight: "2.5rem" }}
        onClick={() => {
          void reloadToNewBuild();
        }}
      >
        <RefreshCw size="0.6875rem" />
        {t("staleBuild.refresh")}
      </button>
    </div>
  );
};
