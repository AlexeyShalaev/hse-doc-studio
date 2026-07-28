import { GraduationCap, Plus, SearchX } from "lucide-react";
import { useTranslation } from "react-i18next";

export type EmptyStateProps = {
  onCreate: () => void;
  /** Непустой запрос → «ничего не нашлось», а не «проектов ещё нет». */
  query?: string | undefined;
  onResetQuery?: (() => void) | undefined;
};

export const EmptyState = ({
  onCreate,
  query,
  onResetQuery,
}: EmptyStateProps) => {
  const { t } = useTranslation("welcome");
  const trimmedQuery = (query ?? "").trim();
  const isSearchMiss = trimmedQuery !== "";

  return (
    <div className="card" style={{ padding: "48px 32px", textAlign: "center" }}>
      <div
        className="flex items-center justify-center"
        style={{
          width: 64,
          height: 64,
          margin: "0 auto 18px",
          borderRadius: 16,
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
          color: "var(--fg-3)",
        }}
      >
        {isSearchMiss ? <SearchX size={32} /> : <GraduationCap size={32} />}
      </div>
      <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
        {isSearchMiss ? t("empty.noMatchTitle") : t("empty.title")}
      </h3>
      <p className="dim" style={{ margin: "8px 0 18px" }}>
        {isSearchMiss
          ? t("empty.noMatchDescription", { query: trimmedQuery })
          : t("empty.description")}
      </p>
      {isSearchMiss ? (
        <button type="button" className="btn" onClick={onResetQuery}>
          <SearchX size={13} />
          {t("empty.resetQuery")}
        </button>
      ) : (
        <button type="button" className="btn primary" onClick={onCreate}>
          <Plus size={13} />
          {t("empty.create")}
        </button>
      )}
    </div>
  );
};
