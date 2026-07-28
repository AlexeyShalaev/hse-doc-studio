import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useFonts } from "../api/fontsQueries";
import { FONT_SAMPLE_SHORT, useInstalledFontFaces } from "../lib/fontPreview";

type FontSelectProps = {
  value: string;
  onChange: (value: string) => void;
  recommended?: string[];
  placeholder?: string | undefined;
};

// Project-side font picker: recommended families (declared by the pack) + fonts
// installed in the Studio (Settings → Шрифты), with a live preview of the chosen
// family. Empty value = "use the pack/document default". Installed fonts preview
// via @font-face (served by the backend); recommended/system families render by
// name if the browser has them, otherwise fall back gracefully.
export const FontSelect = ({
  value,
  onChange,
  recommended = [],
  placeholder,
}: FontSelectProps) => {
  const { t } = useTranslation("settings");
  const { data } = useFonts();
  const installed = useMemo(() => data?.fonts ?? [], [data]);
  const previewByName = useInstalledFontFaces(installed);

  // Family name → synthetic @font-face family, for installed fonts only.
  const installedFamilies = useMemo(() => {
    const list: { family: string; css: string }[] = [];
    const seen = new Set<string>();
    for (const f of installed) {
      const family = f.family || f.name;
      const css = previewByName[f.name];
      if (!css || seen.has(family)) continue;
      seen.add(family);
      list.push({ family, css });
    }
    return list;
  }, [installed, previewByName]);

  const recSet = new Set(recommended);
  const installedOptions = installedFamilies.filter(
    (f) => !recSet.has(f.family),
  );
  const known = new Set<string>([
    ...recommended,
    ...installedFamilies.map((f) => f.family),
  ]);
  const showCustom = value !== "" && !known.has(value);

  const previewFamily = useMemo(() => {
    const hit = installedFamilies.find((f) => f.family === value);
    return hit ? hit.css : value;
  }, [installedFamilies, value]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <select
        className="input"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
        }}
      >
        <option value="">{placeholder ?? t("fonts.pickerDefault")}</option>
        {recommended.length > 0 && (
          <optgroup label={t("fonts.pickerRecommended")}>
            {recommended.map((fam) => (
              <option key={fam} value={fam}>
                {fam}
              </option>
            ))}
          </optgroup>
        )}
        {installedOptions.length > 0 && (
          <optgroup label={t("fonts.pickerInstalled")}>
            {installedOptions.map((f) => (
              <option key={f.family} value={f.family}>
                {f.family}
              </option>
            ))}
          </optgroup>
        )}
        {showCustom && <option value={value}>{value}</option>}
      </select>

      {value !== "" && (
        <div
          title={value}
          style={{
            fontFamily: `'${previewFamily}'`,
            fontSize: 16,
            lineHeight: 1.3,
            color: "var(--fg-1)",
            padding: "5px 9px",
            border: "1px solid var(--border)",
            borderRadius: 6,
            background: "var(--bg-2)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {FONT_SAMPLE_SHORT}
        </div>
      )}
    </div>
  );
};
