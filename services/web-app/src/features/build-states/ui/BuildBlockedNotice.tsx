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
              fontSize: 10.5,
              lineHeight: 1.4,
              color: "var(--fg-2)",
              padding: "6px 8px",
              border: "1px solid var(--c-warn)",
              borderRadius: 4,
            }
          : {
              padding: "12px 16px",
              background: "var(--bg-1)",
              borderBottom: "1px solid var(--c-warn)",
              borderLeft: "3px solid var(--c-warn)",
            }
      }
    >
      <ServerOff
        size={compact ? 12 : 18}
        style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 1 }}
      />
      <div className="flex flex-col" style={{ gap: 3, minWidth: 0, flex: 1 }}>
        <strong style={{ fontSize: compact ? 11 : 13 }}>{title}</strong>
        <span
          style={{
            fontSize: compact ? 10.5 : 12,
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
          style={{ gap: compact ? 8 : 12, marginTop: compact ? 2 : 4 }}
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
              style={{ fontSize: compact ? 10.5 : 12 }}
            >
              {t("compile.unavailable.openRunners")}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
};
