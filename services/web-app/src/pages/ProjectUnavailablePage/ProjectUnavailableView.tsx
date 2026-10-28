import { ArrowLeft, Home, LockKeyhole } from "lucide-react";
import { useTranslation } from "react-i18next";

export type ProjectUnavailableViewProps = {
  onHome: () => void;
  onBack: () => void;
};

/**
 * «Проект не найден или у вас нет доступа»: сервер отвечает одинаково на чужой и
 * на несуществующий проект, поэтому страница не называет причину.
 */
export const ProjectUnavailableView = ({
  onHome,
  onBack,
}: ProjectUnavailableViewProps) => {
  const { t } = useTranslation("projectAccess");
  return (
    <main
      className="flex flex-1 items-center justify-center"
      style={{ padding: 24 }}
      data-testid="project-unavailable"
    >
      <section
        className="flex flex-col"
        style={{
          width: "min(520px, 100%)",
          gap: 16,
          padding: 24,
          border: "1px solid var(--border)",
          borderRadius: "var(--r-3)",
          background: "var(--bg-1)",
          boxShadow: "var(--shadow-1)",
        }}
      >
        <div className="flex items-start" style={{ gap: 14 }}>
          <div
            className="flex items-center justify-center shrink-0"
            style={{
              width: 40,
              height: 40,
              borderRadius: "var(--r-2)",
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              color: "var(--fg-2)",
            }}
          >
            <LockKeyhole size={20} aria-hidden="true" />
          </div>
          <div className="flex flex-col" style={{ gap: 6, minWidth: 0 }}>
            <h1 style={{ margin: 0, fontSize: 20, lineHeight: 1.25 }}>
              {t("unavailable.title")}
            </h1>
            <p
              className="dim"
              style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}
            >
              {t("unavailable.message")}
            </p>
          </div>
        </div>
        <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn primary" onClick={onHome}>
            <Home size={12} />
            {t("unavailable.home")}
          </button>
          <button type="button" className="btn" onClick={onBack}>
            <ArrowLeft size={12} />
            {t("unavailable.back")}
          </button>
        </div>
      </section>
    </main>
  );
};
