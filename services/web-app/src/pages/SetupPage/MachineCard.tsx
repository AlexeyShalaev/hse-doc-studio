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
        borderRadius: "0.625rem",
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
          gridTemplateColumns: "repeat(auto-fit, minmax(8.75rem, 1fr))",
          gap: "0.5625rem 1rem",
          padding: "0.75rem 0.875rem",
          fontSize: "0.78125rem",
        }}
      >
        <Fact icon={<Laptop size="0.8125rem" />} value={OS_LABEL[os]} />
        {engine && (
          <>
            <Fact
              icon={<Container size="0.8125rem" />}
              value={`${engine.operating_system} ${engine.server_version}`}
            />
            <Fact
              icon={<Cpu size="0.8125rem" />}
              value={t("machine.cores", { count: engine.cpus })}
              hint={t("machine.coresHint")}
            />
            <Fact
              icon={<MemoryStick size="0.8125rem" />}
              value={formatBytes(engine.memory_bytes)}
              hint={t("machine.memoryHint")}
            />
          </>
        )}
        {freeBytes !== null && (
          <Fact
            icon={<HardDrive size="0.8125rem" />}
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
          padding: "0.625rem 0.875rem",
          borderTop: "1px solid var(--border)",
          fontSize: "0.78125rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Type
            size="0.8125rem"
            style={{
              opacity: 0.55,
              flexShrink: 0,
              color: fonts?.directory ? undefined : "var(--c-warn)",
            }}
          />
          <span style={{ fontWeight: 600 }}>{t("machine.fontsTitle")}</span>
          <span
            className="dim"
            style={{ marginLeft: "auto", fontSize: "0.6875rem" }}
          >
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
            style={{ padding: "1px 0.3125rem", flexShrink: 0 }}
          >
            <Pencil size="0.6875rem" />
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
              marginTop: "0.4375rem",
              fontFamily: "var(--font-mono, monospace)",
              fontSize: "0.71875rem",
            }}
          />
        ) : (
          <code
            className="dim"
            style={{
              display: "block",
              marginTop: "0.25rem",
              fontSize: "0.71875rem",
              wordBreak: "break-all",
            }}
          >
            {fontsPath || fonts?.directory || "—"}
          </code>
        )}

        <div
          className="dim"
          style={{ fontSize: "0.6875rem", marginTop: "0.3125rem" }}
        >
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
            padding: "0.625rem 0.875rem",
            borderTop: "1px solid var(--border)",
            fontSize: "0.78125rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Package
              size="0.8125rem"
              style={{
                opacity: 0.55,
                flexShrink: 0,
                color: tex.present ? undefined : "var(--c-info)",
              }}
            />
            <span style={{ fontWeight: 600 }}>{t("machine.texTitle")}</span>
            <span
              className="dim"
              style={{ marginLeft: "auto", fontSize: "0.6875rem" }}
            >
              {tex.present ? t("machine.texPresent") : t("machine.texAbsent")}
            </span>
          </div>
          {!tex.present && (
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4375rem",
                marginTop: "0.375rem",
                fontSize: "0.75rem",
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
            padding: "0.5625rem 0.875rem 0",
            borderTop: "1px solid var(--border)",
            fontSize: "0.6875rem",
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
            padding: "0.5rem 0.875rem 0.875rem",
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "0.4375rem 0.875rem",
            fontSize: "0.75rem",
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
      gap: "0.375rem",
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
        fontSize: mono ? "0.71875rem" : undefined,
      }}
    >
      {value}
    </dd>
  </>
);
