import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { CatalogPack } from "@entities/pack-catalog";
import { pickLocalized } from "@shared/lib";
import { Badge } from "@shared/ui";

/** Пак каталога: название, id, скрыт ли из мастера, версии (скрытые помечены). */
export const PackLine = ({
  pack,
  origin,
}: {
  pack: CatalogPack;
  /** Метка, откуда пак: «Встроенный», «Удалённый источник». */
  origin?: string | undefined;
}) => {
  const { t, i18n } = useTranslation("adminPackCatalog");
  return (
    <li
      className="flex flex-col"
      style={{ gap: "0.25rem", padding: "0.5rem 0" }}
      data-testid={`pc-pack-${pack.id}`}
    >
      <div
        className="flex items-center"
        style={{ gap: "0.5rem", flexWrap: "wrap" }}
      >
        <span style={{ fontSize: "0.78125rem", fontWeight: 600 }}>
          {pickLocalized(pack.name, i18n.language, pack.id)}
        </span>
        <span className="mono dimmer" style={{ fontSize: "0.6875rem" }}>
          {pack.id}
        </span>
        {origin && <Badge variant="subtle">{origin}</Badge>}
        {pack.replaces_builtin && (
          <Badge variant="info">{t("pack.replacesBuiltin")}</Badge>
        )}
        {!pack.listed && <Badge variant="warning">{t("pack.hidden")}</Badge>}
      </div>
      {pack.versions.length > 0 && (
        <div className="flex" style={{ gap: "0.25rem", flexWrap: "wrap" }}>
          {pack.versions.map((version) => (
            <span
              key={`${version.template}@${version.version}`}
              className="chip mono"
              style={{
                fontSize: "0.6875rem",
                opacity: version.listed ? 1 : 0.6,
              }}
              title={version.listed ? undefined : t("pack.versionHiddenHint")}
              data-listed={version.listed ? "true" : "false"}
            >
              {version.template} {version.version}
              {!version.listed && ` · ${t("pack.versionHidden")}`}
            </span>
          ))}
        </div>
      )}
    </li>
  );
};

export const PackList = ({ children }: { children: ReactNode }) => (
  <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>{children}</ul>
);
