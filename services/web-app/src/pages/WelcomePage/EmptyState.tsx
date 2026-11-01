import {
  FileArchive,
  GitBranch,
  GraduationCap,
  Plus,
  SearchX,
} from "lucide-react";
import { useTranslation } from "react-i18next";

export type EmptyStateProps = {
  onCreate: () => void;
  /** Клонировать проект из git: второе действие рядом с созданием. */
  onClone?: (() => void) | undefined;
  /** server: загрузить проект из zip локальной Студии. */
  onImport?: (() => void) | undefined;
  /** Непустой запрос → «ничего не нашлось», а не «проектов ещё нет». */
  query?: string | undefined;
  onResetQuery?: (() => void) | undefined;
  /** server: проекты лежат на сервере, подключать папку нечем, есть приглашения. */
  variant?: "local" | "server" | undefined;
  /** Выбран раздел «Мои» или «Организации», и в нём пусто. */
  scopeFiltered?: boolean | undefined;
  onResetScope?: (() => void) | undefined;
};

export const EmptyState = ({
  onCreate,
  onClone,
  onImport,
  query,
  onResetQuery,
  variant = "local",
  scopeFiltered = false,
  onResetScope,
}: EmptyStateProps) => {
  const { t } = useTranslation("welcome");
  const { t: tAccess } = useTranslation("projectAccess");
  const { t: tImport } = useTranslation("projectImport");
  const isServer = variant === "server";
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
        {isSearchMiss
          ? t("empty.noMatchTitle")
          : scopeFiltered
            ? tAccess("empty.scopeTitle")
            : isServer
              ? tAccess("empty.title")
              : t("empty.title")}
      </h3>
      <p
        className="dim"
        style={{ margin: "8px auto 18px", maxWidth: 440, lineHeight: 1.5 }}
      >
        {isSearchMiss
          ? t("empty.noMatchDescription", { query: trimmedQuery })
          : scopeFiltered
            ? tAccess("empty.scopeDescription")
            : isServer
              ? tAccess("empty.description")
              : t("empty.description")}
      </p>
      {isSearchMiss ? (
        <button type="button" className="btn" onClick={onResetQuery}>
          <SearchX size={13} />
          {t("empty.resetQuery")}
        </button>
      ) : scopeFiltered && onResetScope ? (
        <button type="button" className="btn" onClick={onResetScope}>
          {tAccess("scope.all")}
        </button>
      ) : (
        <div
          className="flex items-center justify-center"
          style={{ gap: 8, flexWrap: "wrap" }}
        >
          <button type="button" className="btn primary" onClick={onCreate}>
            <Plus size={13} />
            {t("empty.create")}
          </button>
          {onImport && (
            <button type="button" className="btn" onClick={onImport}>
              <FileArchive size={13} />
              {tImport("empty")}
            </button>
          )}
          {onClone && (
            <button type="button" className="btn" onClick={onClone}>
              <GitBranch size={13} />
              {t("empty.clone")}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
