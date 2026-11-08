import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";

type ProjectAccess = {
  mode: string;
  reasons: string[];
  required_studio?: string | null | undefined;
  stale_packs?: { path: string; studio_version: string } | null | undefined;
};

export type ProjectAccessBannerProps = {
  access: ProjectAccess | undefined;
  templateVersion: string;
};

/**
 * Полоса «только для чтения»: данные проекта записаны более новой Студией, её
 * версии шаблона здесь нет или идёт обновление шаблона. Запись и так запрещена
 * на сервере (423) — полоса объясняет почему и что делать.
 *
 * Если версия шаблона вшита в эту Студию, но её нет в подключённом извне
 * каталоге шаблонов (`stale_packs`), обновлять Студию бесполезно: полоса
 * называет каталог, а не просит новую версию.
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
  const stale = access.stale_packs ?? null;
  const schemaLimited =
    access.reasons.includes("schema_read") ||
    access.reasons.includes("schema_write");
  const lines: string[] = [];
  if (access.reasons.includes("update_in_progress"))
    lines.push(t("access.updating"));
  if (schemaLimited) lines.push(t("access.schema", { required }));
  if (access.reasons.includes("template_missing"))
    lines.push(
      stale
        ? t("access.templateStale", {
            version: templateVersion,
            path: stale.path,
            studio: stale.studio_version,
          })
        : t("access.template", { version: templateVersion, required }),
    );
  // Совет обновить Студию нужен, только если без новой Студии проект не открыть.
  const hint = stale && !schemaLimited ? "access.staleHint" : "access.hint";

  return (
    <div
      role="status"
      style={{
        flexShrink: 0,
        display: "flex",
        alignItems: "flex-start",
        gap: "0.625rem",
        padding: "0.5rem 0.875rem",
        background: "var(--c-warn-soft)",
        borderBottom: "1px solid var(--c-warn)",
        fontSize: "0.75rem",
      }}
    >
      <Lock
        size="0.8125rem"
        style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: "0.125rem" }}
      />
      <div className="flex flex-col" style={{ gap: "0.125rem" }}>
        <strong>
          {access.mode === "files_only"
            ? t("access.filesOnly")
            : t("access.readOnly")}
        </strong>
        {lines.map((line) => (
          <span key={line}>{line}</span>
        ))}
        {!access.reasons.includes("update_in_progress") && (
          <span className="dim">{t(hint)}</span>
        )}
      </div>
    </div>
  );
};
