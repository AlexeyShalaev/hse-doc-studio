import { useTranslation } from "react-i18next";
import { MemoryStick, Zap } from "lucide-react";
import {
  useLoadedModels,
  useUnloadModel,
  type LoadedModel,
} from "@entities/ai-runtime";
import { i18n, toast } from "@shared/lib";

const gb = (bytes: number): string =>
  i18n.t("localRuntime:loaded.gb", { value: (bytes / 1e9).toFixed(1) });

const placement = (m: LoadedModel): string => {
  if (m.vram_bytes <= 0)
    return i18n.t("localRuntime:loaded.inRam", { size: gb(m.size_bytes) });
  if (m.vram_bytes >= m.size_bytes)
    return i18n.t("localRuntime:loaded.inVram", { size: gb(m.size_bytes) });
  return i18n.t("localRuntime:loaded.split", {
    vram: gb(m.vram_bytes),
    ram: gb(m.size_bytes - m.vram_bytes),
  });
};

const expiresIn = (iso: string | null): string | null => {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return null;
  const min = Math.round(ms / 60000);
  if (min <= 0) return i18n.t("localRuntime:loaded.unloadImminent");
  if (min < 60)
    return i18n.t("localRuntime:loaded.autoUnloadMin", { count: min });
  return i18n.t("localRuntime:loaded.autoUnloadHr", {
    count: Math.round(min / 60),
  });
};

export const LoadedModelsSection = () => {
  const { t } = useTranslation("localRuntime");
  const loadedQuery = useLoadedModels();
  const unload = useUnloadModel();

  const models = loadedQuery.data?.models ?? [];
  if (models.length === 0) return null;

  return (
    <div className="flex flex-col" style={{ gap: 6 }}>
      <div
        className="dim"
        style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}
      >
        {t("loaded.heading")}
      </div>
      {models.map((m) => {
        const exp = expiresIn(m.expires_at);
        return (
          <div
            key={m.name}
            className="flex items-center justify-between"
            style={{
              gap: 12,
              padding: "8px 12px",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--bg-1)",
            }}
          >
            <div className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
              <div className="flex items-center" style={{ gap: 8 }}>
                {m.vram_bytes > 0 ? (
                  <Zap size={12} style={{ color: "var(--c-ok)" }} />
                ) : (
                  <MemoryStick size={12} style={{ color: "var(--fg-2)" }} />
                )}
                <span className="mono" style={{ fontSize: 12 }}>
                  {m.name}
                </span>
              </div>
              <span className="dim" style={{ fontSize: 11 }}>
                {placement(m)}
                {exp ? ` · ${exp}` : ""}
              </span>
            </div>
            <button
              type="button"
              className="btn xs"
              disabled={unload.isPending}
              onClick={() => {
                unload.mutate(m.name, {
                  onSuccess: () =>
                    toast.success(t("toast.modelUnloaded", { name: m.name })),
                  onError: () => toast.error(t("toast.unloadFailed")),
                });
              }}
              title={t("loaded.unloadTitle")}
            >
              {t("loaded.unload")}
            </button>
          </div>
        );
      })}
    </div>
  );
};
