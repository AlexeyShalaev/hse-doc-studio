import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Container,
  Cpu,
  HardDrive,
  Laptop,
  MemoryStick,
  Package,
  Pencil,
  Type,
} from "lucide-react";
import { useSetupEnvironment, type ProbeFolderResult } from "@entities/setup";
import { detectHostOs } from "@features/first-run-setup";
import { formatBytes } from "@shared/lib";

type MachineCardProps = {
  probe: ProbeFolderResult | null;
  /** Переопределённый пользователем каталог шрифтов; "" — автоопределение. */
  fontsPath: string;
  onFontsPathChange: (path: string) => void;
  /** Скачать движок LaTeX сразу после настройки. */
  prefetchTex: boolean;
  onPrefetchTexChange: (value: boolean) => void;
};

/** Ниже этого порога места на первую сборку может не хватить. */
const LOW_DISK_BYTES = 8 * 1024 ** 3;

const OS_LABEL: Record<ReturnType<typeof detectHostOs>, string> = {
  windows: "Windows",
  macos: "macOS",
  linux: "Linux",
};

/**
 * Что продукт узнал о машине и с какими параметрами его запустили.
 *
 * Всё это пользователю больше негде посмотреть: «О программе» до окончания
 * настройки недоступна, а команду запуска он мог скопировать не читая. И цифры
 * не справочные — от памяти и ядер, доступных КОНТЕЙНЕРАМ, зависит скорость
 * сборок, а от места на диске то, поместится ли образ TeX Live.
 *
 * Ничего не прячем за раскрытие: раскладка ушла в ширину, места хватает, а
 * лишний клик на стартовом экране — это ещё одна вещь, которую надо заметить.
 */
export const MachineCard = ({
  probe,
  fontsPath,
  onFontsPathChange,
  prefetchTex,
  onPrefetchTexChange,
}: MachineCardProps) => {
  const { t } = useTranslation("setup");
  const { data } = useSetupEnvironment();

  const engine = data?.engine ?? null;
  const container = data?.container ?? null;
  const fonts = data?.fonts ?? null;
  const tex = data?.tex ?? null;
  const [editingFonts, setEditingFonts] = useState(false);
  const os = detectHostOs();
  const freeBytes = probe?.free_bytes ?? null;
  const lowDisk = freeBytes !== null && freeBytes < LOW_DISK_BYTES;

  return (
    <div
      style={{
        borderRadius: 10,
        border: "1px solid var(--border)",
        background: "var(--bg)",
      }}
    >
      {/* auto-fit, а не фиксированные колонки: в узкой боковой колонке
          строится столбиком, а если карточка когда-нибудь окажется во всю
          ширину — раскладывается в ряд без отдельной вёрстки. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "9px 16px",
          padding: "12px 14px",
          fontSize: 12.5,
        }}
      >
        <Fact icon={<Laptop size={13} />} value={OS_LABEL[os]} />
        {engine && (
          <>
            <Fact
              icon={<Container size={13} />}
              value={`${engine.operating_system} ${engine.server_version}`}
            />
            <Fact
              icon={<Cpu size={13} />}
              value={t("machine.cores", { count: engine.cpus })}
              hint={t("machine.coresHint")}
            />
            <Fact
              icon={<MemoryStick size={13} />}
              value={formatBytes(engine.memory_bytes)}
              hint={t("machine.memoryHint")}
            />
          </>
        )}
        {freeBytes !== null && (
          <Fact
            icon={<HardDrive size={13} />}
            value={t("machine.free", { size: formatBytes(freeBytes) })}
            hint={lowDisk ? t("machine.lowDiskHint") : t("machine.freeHint")}
            tone={lowDisk ? "warn" : undefined}
          />
        )}
      </div>

      {/* Каталог шрифтов показываем ВСЕГДА, даже когда всё нашлось: если
          автоопределение промахнулось, узнать об этом надо здесь, а не по
          неверному начертанию в готовом документе. */}
      <div
        style={{
          padding: "10px 14px",
          borderTop: "1px solid var(--border)",
          fontSize: 12.5,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Type
            size={13}
            style={{
              opacity: 0.55,
              flexShrink: 0,
              color: fonts?.directory ? undefined : "var(--c-warn)",
            }}
          />
          <span style={{ fontWeight: 600 }}>{t("machine.fontsTitle")}</span>
          <span className="dim" style={{ marginLeft: "auto", fontSize: 11 }}>
            {fonts?.directory
              ? t("machine.fontsFound", { count: fonts.count })
              : t("machine.fontsMissing")}
          </span>
          <button
            type="button"
            className="btn ghost xs"
            onClick={() => {
              setEditingFonts((value) => !value);
            }}
            style={{ padding: "1px 5px", flexShrink: 0 }}
          >
            <Pencil size={11} />
            {editingFonts ? t("machine.fontsCancel") : t("machine.fontsEdit")}
          </button>
        </div>

        {editingFonts ? (
          <input
            className="input"
            value={fontsPath}
            placeholder={fonts?.directory ?? t("machine.fontsPlaceholder")}
            spellCheck={false}
            autoComplete="off"
            aria-label={t("machine.fontsTitle")}
            onChange={(event) => {
              onFontsPathChange(event.target.value);
            }}
            style={{
              width: "100%",
              marginTop: 7,
              fontFamily: "var(--font-mono, monospace)",
              fontSize: 11.5,
            }}
          />
        ) : (
          <code
            className="dim"
            style={{
              display: "block",
              marginTop: 4,
              fontSize: 11.5,
              wordBreak: "break-all",
            }}
          >
            {fontsPath || fonts?.directory || "—"}
          </code>
        )}

        <div className="dim" style={{ fontSize: 11, marginTop: 5 }}>
          {fonts?.directory
            ? t("machine.fontsHint")
            : t("machine.fontsMissingHint")}
        </div>
      </div>

      {/* Движок LaTeX: не скачан — первая сборка началась бы с многогигабайтной
          загрузки, о которой человек не догадывается. Галочка выключает
          предзагрузку — например, на дорогом мобильном интернете. */}
      {tex && (
        <div
          style={{
            padding: "10px 14px",
            borderTop: "1px solid var(--border)",
            fontSize: 12.5,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Package
              size={13}
              style={{
                opacity: 0.55,
                flexShrink: 0,
                color: tex.present ? undefined : "var(--c-info)",
              }}
            />
            <span style={{ fontWeight: 600 }}>{t("machine.texTitle")}</span>
            <span className="dim" style={{ marginLeft: "auto", fontSize: 11 }}>
              {tex.present ? t("machine.texPresent") : t("machine.texAbsent")}
            </span>
          </div>
          {!tex.present && (
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 7,
                marginTop: 6,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={prefetchTex}
                onChange={(event) => {
                  onPrefetchTexChange(event.target.checked);
                }}
              />
              {t("machine.texPrefetch")}
            </label>
          )}
        </div>
      )}

      {container && (
        <div
          className="dim"
          style={{
            padding: "9px 14px 0",
            borderTop: "1px solid var(--border)",
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          {t("machine.launch")}
        </div>
      )}

      {container && (
        <dl
          style={{
            margin: 0,
            padding: "8px 14px 14px",
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "7px 14px",
            fontSize: 12,
          }}
        >
          <Row label={t("machine.image")} value={container.image} mono />
          <Row
            label={t("machine.port")}
            value={
              container.published_ports.join(", ") || t("machine.notPublished")
            }
            mono
          />
          <Row
            label={t("machine.socket")}
            value={
              container.socket_mounted
                ? t("machine.socketOn")
                : t("machine.socketOff")
            }
          />
          <Row
            label={t("machine.group")}
            value={container.group_add.join(", ") || "—"}
            mono
          />
          <Row
            label={t("machine.restart")}
            value={container.restart_policy}
            mono
          />
          <Row
            label={t("machine.folders")}
            value={
              container.mounts.length > 0
                ? container.mounts
                    .map((m) => `${m.source} → ${m.destination}`)
                    .join("\n")
                : t("machine.noFolders")
            }
            mono
          />
        </dl>
      )}
    </div>
  );
};

type FactProps = {
  icon: React.ReactNode;
  value: string;
  hint?: string | undefined;
  tone?: "warn" | undefined;
};

const Fact = ({ icon, value, hint, tone }: FactProps) => (
  <span
    title={hint}
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      color: tone === "warn" ? "var(--c-warn)" : undefined,
    }}
  >
    <span style={{ display: "flex", opacity: tone === "warn" ? 1 : 0.55 }}>
      {icon}
    </span>
    {value}
  </span>
);

type RowProps = {
  label: string;
  value: string;
  mono?: boolean | undefined;
};

const Row = ({ label, value, mono = false }: RowProps) => (
  <>
    <dt className="dim" style={{ whiteSpace: "nowrap" }}>
      {label}
    </dt>
    <dd
      style={{
        margin: 0,
        minWidth: 0,
        wordBreak: "break-all",
        whiteSpace: "pre-line",
        fontFamily: mono ? "var(--font-mono, monospace)" : undefined,
        fontSize: mono ? 11.5 : undefined,
      }}
    >
      {value}
    </dd>
  </>
);
