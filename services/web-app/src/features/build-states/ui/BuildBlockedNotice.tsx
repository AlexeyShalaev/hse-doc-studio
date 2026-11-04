import { ServerOff } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import type { BuildBlock } from "@entities/compile";
import { LocalStudioLink } from "@entities/local-studio";
import { useCapabilities } from "@entities/session";
import { useBuildBlockText } from "../lib/blockText";

export type BuildBlockedNoticeProps = {
  block: BuildBlock;
  /** compact: узкая панель (подвал списка документов), без отступов плашки. */
  compact?: boolean;
  /** Проект, который предложить открыть в локальной Студии («Собрать локально»). */
  projectId?: string | null;
};

/**
 * Почему «Собрать» не работает на сервере: нет раннера. Подсказывает собрать
 * документ локально в Студии на компьютере, администратору даёт ссылку на «Раннеры».
 */
export const BuildBlockedNotice = ({
  block,
  compact = false,
  projectId = null,
}: BuildBlockedNoticeProps) => {
  const { t } = useTranslation("documents");
  const { t: tLocal } = useTranslation("localStudio");
  const { has } = useCapabilities();
  const isAdmin = has("admin");
  const { title, reason } = useBuildBlockText(block);

  return (
    <div
      role="status"
      data-testid="build-blocked-notice"
      data-reason={block.reason}
      className="flex items-start gap-2"
      style={
        compact
          ? {
              fontSize: "0.65625rem",
              lineHeight: 1.4,
              color: "var(--fg-2)",
              padding: "0.375rem 0.5rem",
              border: "1px solid var(--c-warn)",
              borderRadius: "0.25rem",
            }
          : {
              padding: "0.75rem 1rem",
              background: "var(--bg-1)",
              borderBottom: "1px solid var(--c-warn)",
              borderLeft: "3px solid var(--c-warn)",
            }
      }
    >
      <ServerOff
        size={compact ? "0.75rem" : "1.125rem"}
        style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 1 }}
      />
      <div
        className="flex flex-col"
        style={{ gap: "0.1875rem", minWidth: 0, flex: 1 }}
      >
        <strong style={{ fontSize: compact ? "0.6875rem" : "0.8125rem" }}>
          {title}
        </strong>
        <span
          className="build-blocked-text"
          style={{
            fontSize: compact ? "0.65625rem" : "0.75rem",
            color: "var(--fg-2)",
            lineHeight: 1.5,
          }}
        >
          {reason} {t("compile.unavailable.local")}{" "}
          {isAdmin
            ? t("compile.unavailable.adminSelf")
            : t("compile.unavailable.admin")}
        </span>
        <div
          className="flex items-center flex-wrap"
          style={{
            gap: compact ? "0.5rem" : "0.75rem",
            marginTop: compact ? "0.125rem" : "0.25rem",
          }}
        >
          <LocalStudioLink
            projectId={projectId}
            variant={compact ? "link" : "button"}
            className={compact ? undefined : "xs"}
          >
            {tLocal("link.buildLocally")}
          </LocalStudioLink>
          {isAdmin && (
            <Link
              to="/admin/runners"
              data-testid="build-blocked-runners-link"
              style={{ fontSize: compact ? "0.65625rem" : "0.75rem" }}
            >
              {t("compile.unavailable.openRunners")}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
};
