import { Cloud, Download, User } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CloudEntry } from "@entities/git-server";
import { useProjectRoleLabel } from "@entities/project";
import { localeTag } from "@shared/lib";

export type CloudProjectCardProps = {
  entry: CloudEntry;
  onOpen: () => void;
};

const formatDate = (iso: string | null, locale: string): string => {
  if (iso === null) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
};

/**
 * Облачный проект, которого ещё нет на этом компьютере: нажатие скачивает его в папку проектов
 * и открывает. Слов «git» и «клонировать» здесь нет (docs/design/local-from-cloud.md).
 */
export const CloudProjectCard = ({ entry, onOpen }: CloudProjectCardProps) => {
  const { t } = useTranslation("localStudio");
  const roleLabel = useProjectRoleLabel();
  const { project, server } = entry;
  const updated = formatDate(project.updated_at, localeTag());
  return (
    <div
      className="card hover relative"
      style={{ padding: "1.125rem" }}
      role="button"
      tabIndex={0}
      aria-label={project.name}
      data-project-card={project.id}
      data-testid="cloud-project-card"
      data-cloud-state="remote"
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        onOpen();
      }}
    >
      <div
        className="flex items-center justify-between"
        style={{ marginBottom: "0.75rem" }}
      >
        <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
          <div
            className="flex items-center justify-center shrink-0"
            style={{
              width: "2rem",
              height: "2rem",
              borderRadius: "0.5rem",
              background: "var(--accent-soft, rgba(120,120,255,0.14))",
              color: "var(--accent)",
            }}
          >
            <Cloud size="1rem" aria-hidden="true" />
          </div>
          <span
            className="chip"
            title={t("cloud.badgeTitle", { host: server.host })}
            data-testid="cloud-badge"
          >
            <Cloud size="0.5625rem" aria-hidden="true" />
            {t("cloud.badge")}
          </span>
        </div>
        <button
          type="button"
          className="btn xs primary"
          data-testid="cloud-open"
          onClick={(e) => {
            e.stopPropagation();
            onOpen();
          }}
        >
          <Download size="0.6875rem" aria-hidden="true" />
          {t("cloud.openButton")}
        </button>
      </div>
      <h3
        className="text-fg-0"
        style={{
          margin: "0 0 0.375rem",
          fontSize: "0.9375rem",
          fontWeight: 600,
          lineHeight: 1.3,
        }}
      >
        {project.name}
      </h3>
      <div
        className="flex items-center gap-2 dim"
        style={{
          fontSize: "0.71875rem",
          marginBottom: "0.875rem",
          minWidth: 0,
        }}
      >
        <User
          size="0.6875rem"
          style={{ color: "var(--fg-3)", flexShrink: 0 }}
        />
        <span className="truncate" style={{ minWidth: 0 }}>
          {project.role === "owner"
            ? t("cloud.ownerSelf")
            : t("cloud.ownerUser", { name: project.owner_name })}
        </span>
      </div>
      <div
        className="flex items-center justify-between"
        style={{ paddingTop: "0.75rem", borderTop: "1px solid var(--border)" }}
      >
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
          {t("cloud.notHere")}
        </span>
        <div className="flex items-center gap-2 shrink-0">
          {project.role !== "owner" && (
            <span
              className="chip shrink-0"
              style={{
                fontSize: "0.59375rem",
                height: "1rem",
                padding: "1px 0.375rem",
              }}
            >
              {roleLabel(project.role)}
            </span>
          )}
          {updated !== "" && (
            <span className="mono dim" style={{ fontSize: "0.65625rem" }}>
              {updated}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
