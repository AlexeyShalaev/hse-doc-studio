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
        padding: 18,
        borderStyle: "dashed",
        minHeight: 180,
        background: "transparent",
        color: "var(--fg-2)",
      }}
    >
      <div
        className="flex items-center justify-center"
        style={{
          width: 36,
          height: 36,
          borderRadius: 10,
          background: "var(--accent-soft)",
          color: "var(--accent)",
          marginBottom: 12,
        }}
      >
        <Plus size={20} />
      </div>
      <h3
        className="text-fg-0"
        style={{ margin: 0, fontSize: 14, fontWeight: 600 }}
      >
        {t("newCard.title")}
      </h3>
      <p
        style={{
          margin: "4px 0 0",
          fontSize: 12,
          color: "var(--fg-2)",
          lineHeight: 1.4,
        }}
      >
        {t("newCard.description")}
      </p>
      <div
        className="flex items-center gap-2"
        style={{ marginTop: 14, color: "var(--fg-3)", fontSize: 11 }}
      >
        <span className="kbd">⌘</span>
        <span className="kbd">N</span>
        <span>{t("newCard.shortcutHint")}</span>
      </div>
    </button>
  );
};
