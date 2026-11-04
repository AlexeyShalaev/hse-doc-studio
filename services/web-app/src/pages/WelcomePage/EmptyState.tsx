import {
  FileArchive,
  GitBranch,
  GraduationCap,
  Laptop,
  Plus,
  SearchX,
  Server,
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
  /** server: «Локальная версия»; local: «Подключиться к серверу». */
  onLocalStudio?: (() => void) | undefined;
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
  onLocalStudio,
}: EmptyStateProps) => {
  const { t } = useTranslation("welcome");
  const { t: tLocal } = useTranslation("localStudio");
  const { t: tAccess } = useTranslation("projectAccess");
  const { t: tImport } = useTranslation("projectImport");
  const isServer = variant === "server";
  const trimmedQuery = (query ?? "").trim();
  const isSearchMiss = trimmedQuery !== "";

  return (
    <div className="card" style={{ padding: "3rem 2rem", textAlign: "center" }}>
      <div
        className="flex items-center justify-center"
        style={{
          width: "4rem",
          height: "4rem",
          margin: "0 auto 1.125rem",
          borderRadius: "1rem",
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
          color: "var(--fg-3)",
        }}
      >
        {isSearchMiss ? <SearchX size="2rem" /> : <GraduationCap size="2rem" />}
      </div>
      <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
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
        style={{
          margin: "0.5rem auto 1.125rem",
          maxWidth: "27.5rem",
          lineHeight: 1.5,
        }}
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
          <SearchX size="0.8125rem" />
          {t("empty.resetQuery")}
        </button>
      ) : scopeFiltered && onResetScope ? (
        <button type="button" className="btn" onClick={onResetScope}>
          {tAccess("scope.all")}
        </button>
      ) : (
        <div
          className="flex items-center justify-center"
          style={{ gap: "0.5rem", flexWrap: "wrap" }}
        >
          <button type="button" className="btn primary" onClick={onCreate}>
            <Plus size="0.8125rem" />
            {t("empty.create")}
          </button>
          {onImport && (
            <button type="button" className="btn" onClick={onImport}>
              <FileArchive size="0.8125rem" />
              {tImport("empty")}
            </button>
          )}
          {onClone && (
            <button type="button" className="btn" onClick={onClone}>
              <GitBranch size="0.8125rem" />
              {t("empty.clone")}
            </button>
          )}
          {onLocalStudio && (
            <button
              type="button"
              className="btn"
              onClick={onLocalStudio}
              data-testid="welcome-empty-local-studio"
            >
              {isServer ? (
                <Laptop size="0.8125rem" />
              ) : (
                <Server size="0.8125rem" />
              )}
              {isServer ? tLocal("link.label") : tLocal("welcome.connect")}
            </button>
          )}
        </div>
      )}
      {!isSearchMiss && !scopeFiltered && !isServer && onLocalStudio && (
        <p
          className="dim"
          style={{
            margin: "0.875rem auto 0",
            maxWidth: "27.5rem",
            fontSize: "0.78125rem",
          }}
        >
          {tLocal("welcome.emptyLocal")}
        </p>
      )}
    </div>
  );
};
