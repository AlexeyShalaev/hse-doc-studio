import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { UploadCloud } from "lucide-react";
import { useUploadFont } from "@entities/fonts";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";

const ACCEPT = ".ttf,.otf,.ttc";
const ACCEPTED_EXTENSIONS = [".ttf", ".otf", ".ttc"];

const isFontFile = (file: File): boolean =>
  ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));

export const UploadFontsSource = () => {
  const { t } = useTranslation("settings");
  const upload = useUploadFont();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFiles = async (files: File[]) => {
    const fonts = files.filter(isFontFile);
    if (fonts.length === 0) {
      if (files.length > 0) toast.error(t("fonts.uploadWrongType"));
      return;
    }
    let ok = 0;
    for (const file of fonts) {
      try {
        await upload.mutateAsync(file);
        ok += 1;
      } catch {
        // per-file error toast already shown by the axios interceptor
      }
    }
    if (ok > 0) toast.success(t("fonts.uploadedToast", { count: ok }));
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <input
        ref={fileRef}
        type="file"
        accept={ACCEPT}
        multiple
        onChange={(e) => void handleFiles(Array.from(e.target.files ?? []))}
        style={{ display: "none" }}
      />
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void handleFiles(Array.from(e.dataTransfer.files));
        }}
        disabled={upload.isPending}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          padding: "28px 16px",
          borderRadius: 8,
          border: `1.5px dashed ${dragging ? "var(--accent)" : "var(--border)"}`,
          background: dragging ? "var(--bg-3, var(--bg-2))" : "var(--bg-2)",
          color: "var(--fg-1)",
          cursor: "pointer",
          textAlign: "center",
          transition: "border-color 0.15s, background 0.15s",
        }}
      >
        {upload.isPending ? (
          <Spinner size="sm" />
        ) : (
          <UploadCloud size={26} style={{ color: "var(--accent)" }} />
        )}
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          {dragging ? t("fonts.uploadDropActive") : t("fonts.uploadDropTitle")}
        </span>
        <span style={{ fontSize: 11.5, color: "var(--fg-3)" }}>
          {t("fonts.uploadDropHint")}
        </span>
      </button>
    </div>
  );
};
