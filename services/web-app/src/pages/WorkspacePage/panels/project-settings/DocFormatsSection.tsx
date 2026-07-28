import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { i18n, pickLocalized } from "@shared/lib";
import { SectionCard } from "../SectionCard";
import type { VariantGroup } from "./sectionData";

export type DocFormatsSectionProps = {
  // Уже сгруппированные строки (groupVariantRows) — владелец считает их из тех
  // же хелперов, что и предикат видимости секции.
  groups: readonly VariantGroup[];
  // PATCH {chosen_variant} в полёте — переключатели блокируются целиком.
  isPending: boolean;
  onSelectVariant: (docId: string, variantId: string) => void;
};

export const DocFormatsSection = ({
  groups,
  isPending,
  onSelectVariant,
}: DocFormatsSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionDocFormats")}>
      <div className="flex flex-col" style={{ gap: 4 }}>
        {groups.map((group, groupIndex) => (
          <Fragment key={group.key}>
            {group.title != null && (
              <div
                className="mono dim"
                style={{
                  fontSize: 9.5,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  marginTop: groupIndex > 0 ? 12 : 0,
                  marginBottom: 2,
                }}
              >
                {group.title}
              </div>
            )}
            {group.rows.map(({ def, doc, variants }) => {
              const current = doc.chosen_variant ?? variants[0]?.id;
              const docName = pickLocalized(def.name, i18n.language, def.id);
              return (
                <div
                  key={doc.id}
                  className="flex items-center justify-between gap-3"
                  style={{ padding: "3px 0", flexWrap: "wrap" }}
                >
                  {/* minWidth инлайном: утилиты min-w-0 в сборке Tailwind нет. */}
                  <span
                    className="truncate"
                    style={{ fontSize: 12.5, minWidth: 0 }}
                  >
                    {docName}
                  </span>
                  <div
                    className="seg"
                    style={{ opacity: isPending ? 0.6 : undefined }}
                  >
                    {variants.map((v) => (
                      <button
                        key={v.id}
                        type="button"
                        className={clsx(current === v.id && "active")}
                        disabled={isPending}
                        onClick={() => {
                          if (v.id === current) return;
                          onSelectVariant(doc.id, v.id);
                        }}
                      >
                        {pickLocalized(v.label, i18n.language, v.id)}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </Fragment>
        ))}
        <span className="dim" style={{ fontSize: 11, marginTop: 6 }}>
          {t("projectSettings.docFormatsHint")}
        </span>
      </div>
    </SectionCard>
  );
};
