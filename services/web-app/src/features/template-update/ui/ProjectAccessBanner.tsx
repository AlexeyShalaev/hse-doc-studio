import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";

type ProjectAccess = {
  mode: string;
  reasons: string[];
  required_studio?: string | null | undefined;
};

export type ProjectAccessBannerProps = {
  access: ProjectAccess | undefined;
  templateVersion: string;
};

/**
 * Полоса «только для чтения»: данные проекта записаны более новой Студией, её
 * версии шаблона здесь нет или идёт обновление шаблона. Запись и так запрещена
 * на сервере (423) — полоса объясняет почему и что делать.
 */
export const ProjectAccessBanner = ({
  access,
  templateVersion,
}: ProjectAccessBannerProps) => {
  const { t } = useTranslation("templateUpdate");
  if (!access || access.mode === "full") return null;

  const required = access.required_studio
    ? t("access.requiredSuffix", { version: access.required_studio })
    : "";
  const lines: string[] = [];
  if (access.reasons.includes("update_in_progress"))
    lines.push(t("access.updating"));
  if (
    access.reasons.includes("schema_read") ||
    access.reasons.includes("schema_write")
  )
    lines.push(t("access.schema", { required }));
  if (access.reasons.includes("template_missing"))
    lines.push(t("access.template", { version: templateVersion, required }));

  return (
    <div
      role="status"
      style={{
        flexShrink: 0,
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "8px 14px",
        background: "var(--c-warn-soft)",
        borderBottom: "1px solid var(--c-warn)",
        fontSize: 12,
      }}
    >
      <Lock
        size={13}
        style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 2 }}
      />
      <div className="flex flex-col" style={{ gap: 2 }}>
        <strong>
          {access.mode === "files_only"
            ? t("access.filesOnly")
            : t("access.readOnly")}
        </strong>
        {lines.map((line) => (
          <span key={line}>{line}</span>
        ))}
        {!access.reasons.includes("update_in_progress") && (
          <span className="dim">{t("access.hint")}</span>
        )}
      </div>
    </div>
  );
};
