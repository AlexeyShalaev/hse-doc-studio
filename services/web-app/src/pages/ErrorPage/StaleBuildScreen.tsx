import { useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  handleStaleBuild,
  reloadToNewBuild,
  useStaleBuildStore,
} from "@shared/lib";

/**
 * Граница маршрута поймала ошибку загрузки чанка: вкладка открыта на старой сборке. Вместо «Ошибки
 * приложения» говорим, что вышла новая версия. Сама страница перезагрузится один раз, если можно.
 */
export const StaleBuildScreen = () => {
  const { t } = useTranslation("appChrome");
  const setScreenShown = useStaleBuildStore((state) => state.setScreenShown);

  useEffect(() => {
    setScreenShown(true);
    handleStaleBuild("chunk");
    return () => {
      setScreenShown(false);
    };
  }, [setScreenShown]);

  return (
    <div
      className="flex flex-col h-dvh bg-bg-0"
      style={{ color: "var(--fg-0)" }}
      data-testid="stale-build-screen"
    >
      <main
        className="flex flex-1 items-center justify-center"
        style={{ padding: "1.5rem" }}
      >
        <section
          role="alert"
          className="flex flex-col"
          style={{
            width: "min(32.5rem, 100%)",
            gap: "0.875rem",
            padding: "1.125rem",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-3)",
            background: "var(--bg-1)",
            boxShadow: "var(--shadow-1)",
          }}
        >
          <h1 style={{ margin: 0, fontSize: "1.25rem", lineHeight: 1.2 }}>
            {t("staleBuild.title")}
          </h1>
          <p
            className="dim"
            style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}
          >
            {t("staleBuild.message")}
          </p>
          <p
            className="dim"
            style={{ margin: 0, fontSize: "0.75rem", lineHeight: 1.5 }}
          >
            {t("staleBuild.saveHint")}
          </p>
          <div>
            <button
              type="button"
              className="btn"
              data-testid="stale-build-refresh"
              style={{ minHeight: "2.5rem" }}
              onClick={() => {
                void reloadToNewBuild();
              }}
            >
              <RefreshCw size="0.75rem" />
              {t("staleBuild.refresh")}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
};
