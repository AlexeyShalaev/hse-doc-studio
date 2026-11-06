import { useTranslation } from "react-i18next";
import { Badge, Section } from "@shared/ui";
import type { Capabilities } from "../api/schemas";
import { gbOf } from "../lib/format";

/** Железо, на котором работает Студия, и пригодность движков. Подсказки идут из пробы железа. */
export const HardwarePanel = ({ caps }: { caps: Capabilities }) => {
  const { t } = useTranslation("adminModelServers");
  const hw = caps.hardware;
  const gb = (mb: number | null) => {
    const value = gbOf(mb);
    return value === null ? t("hardware.unknown") : t("hardware.gb", { value });
  };
  const gpu =
    hw.gpu_vendor === "none"
      ? t("hardware.noGpu")
      : `${hw.gpu_name ?? hw.gpu_vendor}${hw.vram_mb ? ` · ${gb(hw.vram_mb)}` : ""}`;
  const rows: [string, string][] = [
    [t("hardware.gpu"), gpu],
    [t("hardware.ram"), gb(hw.total_ram_mb)],
    [
      t("hardware.cpu"),
      hw.cpu_count === null ? t("hardware.unknown") : String(hw.cpu_count),
    ],
    [t("hardware.arch"), hw.arch ?? t("hardware.unknown")],
    [t("hardware.disk"), gb(hw.disk_free_mb)],
  ];
  return (
    <Section
      title={t("hardware.title")}
      description={t("hardware.lead")}
      testId="ms-hardware"
    >
      <dl
        className="grid"
        style={{
          gap: "0.75rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(9rem, 1fr))",
          padding: "0.75rem 1rem",
          margin: 0,
        }}
      >
        {rows.map(([label, value]) => (
          <div key={label} style={{ minWidth: 0 }}>
            <dt className="dim" style={{ fontSize: "0.75rem" }}>
              {label}
            </dt>
            <dd
              style={{
                margin: 0,
                fontSize: "0.875rem",
                overflowWrap: "anywhere",
              }}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <ul
        className="flex flex-wrap"
        style={{
          gap: "0.5rem",
          padding: "0 1rem 0.75rem",
          margin: 0,
          listStyle: "none",
        }}
      >
        {caps.engines.map((e) => (
          <li key={e.engine} data-testid={`ms-engine-${e.engine}`}>
            <Badge variant={e.available ? "success" : "warning"}>
              {t(`engine.${e.engine}`)}
              {": "}
              {e.available
                ? t("hardware.engineOk")
                : e.reasons
                    .map((r) => t(`reason.${r}`, { defaultValue: r }))
                    .join(", ")}
            </Badge>
          </li>
        ))}
      </ul>
    </Section>
  );
};
