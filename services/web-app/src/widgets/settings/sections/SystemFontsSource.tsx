import { useState } from "react";
import { useTranslation } from "react-i18next";
import { HardDriveDownload, Search } from "lucide-react";
import {
  FONT_SAMPLE_SHORT,
  useImportSystemFonts,
  useSystemFonts,
} from "@entities/fonts";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";

export const SystemFontsSource = () => {
  const { t } = useTranslation("settings");
  const { data, isLoading } = useSystemFonts(true);
  const importFonts = useImportSystemFonts();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const q = query.trim().toLowerCase();
  const allFonts = data?.fonts ?? [];
  const visible = q
    ? allFonts.filter(
        (f) =>
          f.name.toLowerCase().includes(q) ||
          f.family.toLowerCase().includes(q),
      )
    : allFonts;

  const toggle = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleImport = () => {
    const paths = [...selected];
    if (paths.length === 0) return;
    importFonts.mutate(paths, {
      onSuccess: (res) => {
        toast.success(
          t("fonts.importedSystemToast", { count: res.installed.length }),
        );
        setSelected(new Set());
      },
      onError: (err) => toast.error(String(err)),
    });
  };

  if (isLoading) return <Spinner size="sm" />;

  // Пусто теперь означает ровно то, что написано: заглянуть в каталог шрифтов
  // хоста не удалось. Раньше здесь висела команда монтирования — приложение
  // просило человека сделать руками то, что умеет само (см. DockerHostFontProvider).
  if (!data?.available) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <p style={{ fontSize: 12, color: "var(--fg-3)", margin: 0 }}>
          {t("fonts.systemUnavailable")}
        </p>
        <p style={{ fontSize: 11.5, color: "var(--fg-3)", margin: 0 }}>
          {t("fonts.systemUnavailableHint")}
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <p style={{ fontSize: 11.5, color: "var(--fg-3)", margin: 0 }}>
        {t("fonts.systemHint")}
      </p>

      <div
        className="flex items-center"
        style={{
          gap: 6,
          padding: "5px 8px",
          border: "1px solid var(--border)",
          borderRadius: 6,
          background: "var(--bg-2)",
        }}
      >
        <Search size={13} style={{ color: "var(--fg-3)", flexShrink: 0 }} />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
          }}
          placeholder={t("fonts.systemSearch")}
          style={{
            flex: 1,
            border: "none",
            background: "transparent",
            outline: "none",
            fontSize: 12,
            color: "var(--fg-0)",
          }}
        />
      </div>

      <div
        style={{
          maxHeight: 320,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
        {visible.length === 0 ? (
          <p style={{ fontSize: 12, color: "var(--fg-3)", margin: "6px 0" }}>
            {t("fonts.systemNoMatch")}
          </p>
        ) : (
          visible.map((f) => {
            const checked = f.already_installed || selected.has(f.path);
            return (
              <label
                key={f.path}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 10px",
                  borderRadius: 6,
                  border: "1px solid var(--border)",
                  background: "var(--bg-2)",
                  cursor: f.already_installed ? "default" : "pointer",
                  opacity: f.already_installed ? 0.55 : 1,
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={f.already_installed}
                  onChange={() => {
                    toggle(f.path);
                  }}
                  style={{ flexShrink: 0 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  {f.family && (
                    <div
                      style={{
                        fontFamily: `'${f.family}'`,
                        fontSize: 16,
                        lineHeight: 1.25,
                        color: "var(--fg-0)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={f.family}
                    >
                      {FONT_SAMPLE_SHORT}
                    </div>
                  )}
                  <div
                    className="mono"
                    style={{
                      fontSize: 11,
                      color: "var(--fg-3)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {f.family || f.name}
                    {f.family ? ` · ${f.name}` : ""}
                  </div>
                </div>
                {f.already_installed && (
                  <span
                    style={{
                      fontSize: 10,
                      color: "var(--fg-3)",
                      flexShrink: 0,
                    }}
                  >
                    {t("fonts.installed")}
                  </span>
                )}
              </label>
            );
          })
        )}
      </div>

      <div className="flex items-center justify-between">
        <span style={{ fontSize: 11, color: "var(--fg-3)" }}>
          {t("fonts.systemSelected", { count: selected.size })}
        </span>
        <button
          className="btn btn-primary"
          onClick={handleImport}
          disabled={selected.size === 0 || importFonts.isPending}
          style={{ fontSize: 12, gap: 6 }}
        >
          {importFonts.isPending ? (
            <Spinner size="sm" />
          ) : (
            <HardDriveDownload size={14} />
          )}
          {t("fonts.importSelected", { count: selected.size })}
        </button>
      </div>
    </div>
  );
};
