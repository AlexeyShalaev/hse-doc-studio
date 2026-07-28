import { useTranslation } from "react-i18next";
import { FontSelect } from "@entities/fonts";
import { i18n, pickLocalized } from "@shared/lib";
import { SectionCard } from "../SectionCard";
import type { VersionDetail } from "./sectionData";

// Fallback font slots for packs that don't declare their own `type: font`
// meta fields — the fonts section is available in every project.
const DEFAULT_FONT_SLOTS = [
  {
    key: "font_main",
    labelKey: "projectSettings.fontMain",
    recommended: ["Times New Roman", "PT Serif", "Liberation Serif", "Tinos"],
  },
  {
    key: "font_sans",
    labelKey: "projectSettings.fontSans",
    recommended: ["Arial", "PT Sans", "Liberation Sans", "Arimo"],
  },
  {
    key: "font_mono",
    labelKey: "projectSettings.fontMono",
    recommended: ["Consolas", "Courier New", "PT Mono", "JetBrains Mono"],
  },
] as const;

export type FontsSectionProps = {
  versionDetail: VersionDetail | undefined;
  // project.meta с наложенными несохранёнными правками (effective.meta).
  meta: Record<string, unknown> | undefined;
  onChange: (key: string, value: string) => void;
};

export const FontsSection = ({
  versionDetail,
  meta,
  onChange,
}: FontsSectionProps) => {
  const { t } = useTranslation("workspace");

  // Document fonts are a first-class project setting: the pack's `type: font`
  // meta fields supply labels/recommendations when declared; otherwise the
  // three standard slots keep the feature available in every project.
  const packFontFields = Object.entries(
    versionDetail?.meta_fields ?? {},
  ).filter(([, def]) => def.type === "font");
  const fontSlots =
    packFontFields.length > 0
      ? packFontFields.map(([key, def]) => ({
          key,
          label: pickLocalized(def.label, i18n.language, key),
          recommended: def.options ?? [],
          placeholder: def.placeholder ?? undefined,
        }))
      : DEFAULT_FONT_SLOTS.map((slot) => ({
          key: slot.key,
          label: t(slot.labelKey),
          recommended: slot.recommended,
          placeholder: slot.recommended[0],
        }));

  return (
    <SectionCard title={t("projectSettings.sectionFonts")} fullSpan>
      <span className="dim" style={{ fontSize: 11.5 }}>
        {t("projectSettings.fontsHint")}
      </span>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          gap: 12,
          marginTop: 10,
        }}
      >
        {fontSlots.map((slot) => (
          <div key={slot.key} className="field">
            <label>{slot.label}</label>
            <FontSelect
              value={(meta?.[slot.key] as string | undefined) ?? ""}
              recommended={[...slot.recommended]}
              placeholder={slot.placeholder}
              onChange={(v) => {
                onChange(slot.key, v);
              }}
            />
          </div>
        ))}
      </div>
    </SectionCard>
  );
};
