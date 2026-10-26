import { useTranslation } from "react-i18next";
import type { OperationWarning } from "@entities/git-sync";
import { Notice, type NoticeTone } from "@shared/ui/ConflictKit";

export type SyncWarningsProps = {
  warnings: OperationWarning[];
};

const KNOWN = new Set([
  "template_missing_after_merge",
  "signatures_stale",
  "unsafe_path",
  "case_collision",
  "frozen_documents",
  "team_foreign_edit",
  "template_missing",
  "lfs_pointers",
]);

// Что отнимает у человека возможность работать, то предупреждение; что просто
// стоит знать, то справка.
const TONE: Record<string, NoticeTone> = {
  frozen_documents: "info",
  team_foreign_edit: "info",
};

const WarningBody = ({ warning }: { warning: OperationWarning }) => {
  const { t } = useTranslation("gitConflicts");
  const key = KNOWN.has(warning.code) ? warning.code : "unknown";
  const paths = warning.paths;
  return (
    <span className="flex flex-col" style={{ gap: 2 }}>
      <strong>{t(`warnings.${key}.title`)}</strong>
      <span>{t(`warnings.${key}.text`, { code: warning.code })}</span>
      {paths.length > 0 && (
        <details className="warning-paths">
          <summary>{t("warnings.files", { count: paths.length })}</summary>
          <ul>
            {paths.map((path) => (
              <li key={path} className="mono" style={{ fontSize: 11 }}>
                {path}
              </li>
            ))}
          </ul>
        </details>
      )}
    </span>
  );
};

/**
 * Предупреждения слияния над списком файлов: шаблона нет в этой Студии, подписи
 * устарели, часть путей пропущена. Каждое показано отдельной строкой с
 * пояснением; пути под ними раскрываются по щелчку.
 */
export const SyncWarnings = ({ warnings }: SyncWarningsProps) => {
  const { t } = useTranslation("gitConflicts");
  if (warnings.length === 0) return null;
  return (
    <section className="conflict-warnings" aria-label={t("warnings.aria")}>
      {warnings.map((warning) => (
        <Notice
          key={warning.code}
          tone={TONE[warning.code] ?? "warn"}
          role="status"
          text={<WarningBody warning={warning} />}
        />
      ))}
    </section>
  );
};
