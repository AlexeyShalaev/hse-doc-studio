import { useTranslation } from "react-i18next";
import { usePacksSource } from "@entities/system";
import { Spinner } from "@shared/ui/Spinner";
import { Setting } from "./Setting";

const SMALL = { fontSize: "0.71875rem" } as const;

/**
 * Откуда Студия взяла шаблоны и какие версии в них есть. Подключённый извне
 * каталог (папка поверх /app/packs или другой HSE_STUDIO__PACKS_DIR) после
 * обновления Студии остаётся прежним: здесь видно, чем он отстаёт.
 */
export const AboutTemplates = () => {
  const { t } = useTranslation("settings");
  const { data, isLoading } = usePacksSource();

  if (isLoading) {
    return (
      <Setting anchorId="about-templates" label={t("about.templates")}>
        <Spinner size="sm" />
      </Setting>
    );
  }
  if (!data) return null;

  const source =
    data.kind === "builtin"
      ? t("about.templatesBuiltin", { version: data.studio_version })
      : data.kind === "external"
        ? t("about.templatesExternal", { path: data.path })
        : t("about.templatesSource", { path: data.path });
  const missing = data.templates.flatMap((tpl) =>
    tpl.missing.map((v) => `${tpl.template_id} ${v}`),
  );

  return (
    <Setting anchorId="about-templates" label={t("about.templates")}>
      <div className="flex flex-col" style={{ gap: "0.25rem" }}>
        <span className="mono" style={SMALL}>
          {source}
        </span>
        {data.host_path && (
          <span className="mono dim" style={SMALL}>
            {t("about.templatesHost", { path: data.host_path })}
          </span>
        )}
        {data.lagging && (
          <span
            role="status"
            style={{ fontSize: "0.6875rem", color: "var(--c-warn)" }}
          >
            {t("about.templatesLagging", {
              version: data.studio_version,
              missing: missing.join(", "),
            })}
          </span>
        )}
        <details>
          <summary className="dim" style={{ fontSize: "0.6875rem" }}>
            {t("about.templatesVersions")}
          </summary>
          <ul
            className="flex flex-col"
            style={{ gap: "0.125rem", margin: 0, paddingLeft: "1rem" }}
          >
            {data.templates.map((tpl) => (
              <li
                key={`${tpl.pack_id}/${tpl.template_id}`}
                className="mono"
                style={SMALL}
              >
                {`${tpl.pack_id}/${tpl.template_id}: ${tpl.versions.join(", ")}`}
                {tpl.missing.length > 0 && (
                  <span style={{ color: "var(--c-warn)" }}>
                    {` (${t("about.templatesMissing", { versions: tpl.missing.join(", ") })})`}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
      </div>
    </Setting>
  );
};
