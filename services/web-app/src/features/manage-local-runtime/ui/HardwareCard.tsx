import { useTranslation } from "react-i18next";
import { AlertTriangle, Cpu, Info, MemoryStick, Microchip } from "lucide-react";
import { i18n } from "@shared/lib";
import type { HardwareInfo } from "@entities/ai-runtime";

const gb = (mb: number | null): string =>
  mb == null
    ? i18n.t("localRuntime:hardware.empty")
    : i18n.t("localRuntime:hardware.gb", {
        value: String(Math.round(mb / 1024)),
      });

const gpuLabel = (hw: HardwareInfo): string => {
  if (hw.gpu_vendor === "none")
    return i18n.t("localRuntime:hardware.gpuNotDetected");
  const name = hw.gpu_name ?? hw.gpu_vendor.toUpperCase();
  return hw.vram_mb ? `${name} · ${gb(hw.vram_mb)}` : name;
};

type NoteTone = "ok" | "warn" | "dim";
type Note = { tone: NoteTone; key: string };

const gpuNote = (hw: HardwareInfo): Note => {
  switch (hw.gpu_vendor) {
    case "nvidia":
      return hw.docker_gpu_supported
        ? { tone: "ok", key: "hardware.note.nvidiaSupported" }
        : { tone: "warn", key: "hardware.note.nvidiaUnsupported" };
    case "apple":
      return { tone: "warn", key: "hardware.note.apple" };
    case "amd":
      return { tone: "warn", key: "hardware.note.amd" };
    default:
      return { tone: "dim", key: "hardware.note.none" };
  }
};

const TONE_COLOR: Record<NoteTone, string> = {
  ok: "var(--c-ok)",
  warn: "var(--c-warn)",
  dim: "var(--fg-2)",
};

type StatProps = { icon: React.ReactNode; label: string; value: string };

const Stat = ({ icon, label, value }: StatProps) => (
  <div className="flex items-center" style={{ gap: 8, minWidth: 0 }}>
    <span style={{ color: "var(--fg-2)", display: "inline-flex" }}>{icon}</span>
    <div className="flex flex-col" style={{ minWidth: 0 }}>
      <span
        className="dim"
        style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.4 }}
      >
        {label}
      </span>
      <span style={{ fontSize: 12, fontWeight: 500 }} title={value}>
        {value}
      </span>
    </div>
  </div>
);

export type HardwareCardProps = { hardware: HardwareInfo };

export const HardwareCard = ({ hardware }: HardwareCardProps) => {
  const { t } = useTranslation("localRuntime");
  const note = gpuNote(hardware);
  return (
    <div
      className="flex flex-col"
      style={{
        gap: 10,
        padding: 12,
        borderRadius: 6,
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div
        className="grid"
        style={{ gridTemplateColumns: "1.4fr 1fr 1fr", gap: 12 }}
      >
        <Stat
          icon={<Microchip size={14} />}
          label={t("hardware.gpuLabel")}
          value={gpuLabel(hardware)}
        />
        <Stat
          icon={<MemoryStick size={14} />}
          label={t("hardware.ramLabel")}
          value={gb(hardware.total_ram_mb)}
        />
        <Stat
          icon={<Cpu size={14} />}
          label={t("hardware.cpuLabel")}
          value={
            hardware.cpu_count
              ? t("hardware.cpuCores", { count: hardware.cpu_count })
              : t("hardware.empty")
          }
        />
      </div>
      <div
        className="flex items-start"
        style={{ gap: 6, fontSize: 11, color: TONE_COLOR[note.tone] }}
      >
        {note.tone === "warn" ? (
          <AlertTriangle size={12} style={{ marginTop: 1, flexShrink: 0 }} />
        ) : (
          <Info size={12} style={{ marginTop: 1, flexShrink: 0 }} />
        )}
        <span>{t(note.key)}</span>
      </div>
    </div>
  );
};
