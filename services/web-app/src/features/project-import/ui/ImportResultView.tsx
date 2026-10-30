import { CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatFileSize } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import type { ProjectImportResult } from "@entities/session";

// Итог импорта: что перенесено и что стоит знать (предупреждения сервера по кодам).
export const ImportResultView = ({
  result,
}: {
  result: ProjectImportResult;
}) => {
  const { t } = useTranslation("projectImport");
  const facts = [
    t("done.files", { count: result.files }),
    formatFileSize(result.bytes),
    ...(result.chats > 0 ? [t("done.chats", { count: result.chats })] : []),
  ];
  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="project-import-done"
    >
      <div className="flex items-start" style={{ gap: 12 }}>
        <CheckCircle2
          size={22}
          aria-hidden="true"
          style={{ color: "var(--c-ok)", flexShrink: 0, marginTop: 1 }}
        />
        <div style={{ minWidth: 0 }}>
          <div
            style={{ fontSize: 13.5, fontWeight: 600, color: "var(--fg-0)" }}
          >
            {t("done.title")}
          </div>
          <p
            className="dim"
            style={{ margin: "4px 0 0", fontSize: 12.5, lineHeight: 1.5 }}
          >
            {t("done.lead", { name: result.name })}
          </p>
          <p className="mono dim" style={{ margin: "6px 0 0", fontSize: 11.5 }}>
            {facts.join(" · ")}
          </p>
        </div>
      </div>
      {result.id_regenerated && (
        <Notice tone="info" role="status" text={t("done.regenerated")} />
      )}
      {result.warnings.length > 0 && (
        <div className="flex flex-col" style={{ gap: 6 }}>
          <div
            className="dim"
            style={{
              fontSize: 11,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            {t("done.warningsTitle")}
          </div>
          {result.warnings.map((warning) => (
            <Notice
              key={warning.code}
              tone="warn"
              role="status"
              text={t(`warnings.${warning.code}`, {
                count: Number.parseInt(warning.detail, 10) || 1,
              })}
            />
          ))}
        </div>
      )}
    </div>
  );
};
