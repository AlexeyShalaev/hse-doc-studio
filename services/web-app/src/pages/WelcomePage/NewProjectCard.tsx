import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";

export type NewProjectCardProps = {
  onClick: () => void;
};

export const NewProjectCard = ({ onClick }: NewProjectCardProps) => {
  const { t } = useTranslation("welcome");
  return (
    <button
      type="button"
      onClick={onClick}
      className="card hover text-left cursor-pointer flex flex-col items-start justify-center"
      style={{
        padding: "1.125rem",
        borderStyle: "dashed",
        minHeight: "11.25rem",
        background: "transparent",
        color: "var(--fg-2)",
      }}
    >
      <div
        className="flex items-center justify-center"
        style={{
          width: "2.25rem",
          height: "2.25rem",
          borderRadius: "0.625rem",
          background: "var(--accent-soft)",
          color: "var(--accent)",
          marginBottom: "0.75rem",
        }}
      >
        <Plus size="1.25rem" />
      </div>
      <h3
        className="text-fg-0"
        style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600 }}
      >
        {t("newCard.title")}
      </h3>
      <p
        style={{
          margin: "0.25rem 0 0",
          fontSize: "0.75rem",
          color: "var(--fg-2)",
          lineHeight: 1.4,
        }}
      >
        {t("newCard.description")}
      </p>
      <div
        className="flex items-center gap-2"
        style={{
          marginTop: "0.875rem",
          color: "var(--fg-3)",
          fontSize: "0.6875rem",
        }}
      >
        <span className="kbd">⌘</span>
        <span className="kbd">N</span>
        <span>{t("newCard.shortcutHint")}</span>
      </div>
    </button>
  );
};
