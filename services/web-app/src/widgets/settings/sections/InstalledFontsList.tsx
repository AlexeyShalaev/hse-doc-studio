import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, Type } from "lucide-react";
import {
  FONT_SAMPLE_SHORT,
  formatFontSize,
  useDeleteFont,
  useFonts,
  useInstalledFontFaces,
  type InstalledFont,
} from "@entities/fonts";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";

type FontRowProps = {
  font: InstalledFont;
  previewFamily: string | undefined;
};

const FontRow = ({ font, previewFamily }: FontRowProps) => {
  const { t } = useTranslation("settings");
  const del = useDeleteFont();

  const handleDelete = () => {
    if (!confirm(t("fonts.deleteConfirm", { name: font.name }))) return;
    del.mutate(font.name, {
      onSuccess: () =>
        toast.success(t("fonts.deletedToast", { name: font.name })),
      onError: (err) => toast.error(String(err)),
    });
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.625rem",
        padding: "0.5rem 0.625rem",
        borderRadius: "0.375rem",
        border: "1px solid var(--border)",
        background: "var(--bg-2)",
      }}
    >
      <Type
        size="0.9375rem"
        style={{ color: "var(--accent)", flexShrink: 0 }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: previewFamily ? `'${previewFamily}'` : undefined,
            fontSize: "1rem",
            lineHeight: 1.25,
            color: "var(--fg-0)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {FONT_SAMPLE_SHORT}
        </div>
        <div
          className="mono"
          style={{
            fontSize: "0.6875rem",
            color: "var(--fg-3)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {font.name}
          {font.family ? ` · ${font.family}` : ""}
        </div>
      </div>
      <span
        style={{ fontSize: "0.6875rem", color: "var(--fg-3)", flexShrink: 0 }}
      >
        {formatFontSize(font.size_bytes)}
      </span>
      <button
        className="btn btn-ghost icon"
        onClick={handleDelete}
        disabled={del.isPending}
        title={t("fonts.delete")}
        style={{ padding: "0.25rem", color: "var(--fg-2)" }}
      >
        {del.isPending ? <Spinner size="sm" /> : <Trash2 size="0.875rem" />}
      </button>
    </div>
  );
};

export const InstalledFontsList = () => {
  const { t } = useTranslation("settings");
  const { data, isLoading } = useFonts();

  const fonts = useMemo(() => data?.fonts ?? [], [data]);
  const previewFamilies = useInstalledFontFaces(fonts);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>
        {t("fonts.installedTitle")}
        {fonts.length > 0 && (
          <span style={{ color: "var(--fg-3)", fontWeight: 400 }}>
            {" "}
            · {fonts.length}
          </span>
        )}
      </span>

      {isLoading ? (
        <Spinner size="sm" />
      ) : fonts.length === 0 ? (
        <p style={{ fontSize: "0.75rem", color: "var(--fg-3)", margin: 0 }}>
          {t("fonts.empty")}
        </p>
      ) : (
        <div
          style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}
        >
          {fonts.map((f) => (
            <FontRow
              key={f.name}
              font={f}
              previewFamily={previewFamilies[f.name]}
            />
          ))}
        </div>
      )}
    </div>
  );
};
