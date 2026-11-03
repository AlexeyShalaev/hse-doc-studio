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
      style={{ padding: 18 }}
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
        style={{ marginBottom: 12 }}
      >
        <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
          <div
            className="flex items-center justify-center shrink-0"
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "var(--accent-soft, rgba(120,120,255,0.14))",
              color: "var(--accent)",
            }}
          >
            <Cloud size={16} aria-hidden="true" />
          </div>
          <span
            className="chip"
            title={t("cloud.badgeTitle", { host: server.host })}
            data-testid="cloud-badge"
          >
            <Cloud size={9} aria-hidden="true" />
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
          <Download size={11} aria-hidden="true" />
          {t("cloud.openButton")}
        </button>
      </div>
      <h3
        className="text-fg-0"
        style={{
          margin: "0 0 6px",
          fontSize: 15,
          fontWeight: 600,
          lineHeight: 1.3,
        }}
      >
        {project.name}
      </h3>
      <div
        className="flex items-center gap-2 dim"
        style={{ fontSize: 11.5, marginBottom: 14, minWidth: 0 }}
      >
        <User size={11} style={{ color: "var(--fg-3)", flexShrink: 0 }} />
        <span className="truncate" style={{ minWidth: 0 }}>
          {project.role === "owner"
            ? t("cloud.ownerSelf")
            : t("cloud.ownerUser", { name: project.owner_name })}
        </span>
      </div>
      <div
        className="flex items-center justify-between"
        style={{ paddingTop: 12, borderTop: "1px solid var(--border)" }}
      >
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("cloud.notHere")}
        </span>
        <div className="flex items-center gap-2 shrink-0">
          {project.role !== "owner" && (
            <span
              className="chip shrink-0"
              style={{ fontSize: 9.5, height: 16, padding: "1px 6px" }}
            >
              {roleLabel(project.role)}
            </span>
          )}
          {updated !== "" && (
            <span className="mono dim" style={{ fontSize: 10.5 }}>
              {updated}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
