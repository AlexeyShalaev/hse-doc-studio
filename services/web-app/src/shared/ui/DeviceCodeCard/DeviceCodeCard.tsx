import { useEffect, useState, type ReactNode } from "react";
import { CircleAlert, CircleCheck, CircleX, Link2 } from "lucide-react";

// Общие части страниц подтверждения кода устройства: сопряжение раннера
// (/settings/runners/pair) и вход Студии в git сервера (/device). Каркас,
// крупный код, сведения об устройстве, отсчёт срока и итог одинаковы, тексты
// и testid задаёт страница.

const MS_PER_MINUTE = 60_000;
const MS_PER_SECOND = 1000;
const CODE_HALF = 4;
const CODE_LENGTH = CODE_HALF * 2;
/** Алфавит кода устройства без похожих букв; тот же, что core/device_codes.py сервера. */
export const DEVICE_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789";

/** Оставшееся время кода: «8:42»; null, если срок вышел. */
export const deviceCountdown = (
  expiresAt: string,
  now: number,
): string | null => {
  const left = Date.parse(expiresAt) - now;
  if (Number.isNaN(left) || left <= 0) return null;
  const minutes = Math.floor(left / MS_PER_MINUTE);
  const seconds = Math.floor((left % MS_PER_MINUTE) / MS_PER_SECOND);
  return `${String(minutes)}:${String(seconds).padStart(2, "0")}`;
};

/** Код без учёта регистра, пробелов и дефиса; негодный даёт null. */
export const normalizeDeviceCode = (input: string): string | null => {
  const raw = input.toUpperCase().replace(/[\s-]/g, "");
  if (raw.length !== CODE_LENGTH) return null;
  for (let i = 0; i < raw.length; i += 1) {
    if (!DEVICE_CODE_ALPHABET.includes(raw.charAt(i))) return null;
  }
  return `${raw.slice(0, CODE_HALF)}-${raw.slice(CODE_HALF)}`;
};

/** Маска ввода: буквы и цифры, дефис после четвёртого знака. */
export const maskDeviceCode = (input: string): string => {
  const raw = input
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .slice(0, CODE_LENGTH);
  return raw.length > CODE_HALF
    ? `${raw.slice(0, CODE_HALF)}-${raw.slice(CODE_HALF)}`
    : raw;
};

/** Текущее время раз в секунду: для обратного отсчёта срока кода. */
export const useNowTick = (stepMs = MS_PER_SECOND): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, stepMs);
    return () => {
      window.clearInterval(id);
    };
  }, [stepMs]);
  return now;
};

/** Каркас страницы: карточка по центру с подписью сверху. */
export const DeviceCodeShell = ({
  caption,
  testId,
  children,
}: {
  caption: string;
  testId: string;
  children: ReactNode;
}) => (
  <main
    className="flex flex-1 items-center justify-center"
    style={{ padding: 24, overflowY: "auto" }}
    data-testid={testId}
  >
    <section
      className="flex flex-col"
      style={{
        width: "min(520px, 100%)",
        gap: 16,
        padding: 24,
        border: "1px solid var(--border)",
        borderRadius: "var(--r-3)",
        background: "var(--bg-1)",
        boxShadow: "var(--shadow-1)",
      }}
    >
      <span
        className="flex items-center"
        style={{ gap: 8, fontSize: 12, color: "var(--fg-2)" }}
      >
        <Link2 size={14} aria-hidden="true" />
        {caption}
      </span>
      {children}
    </section>
  </main>
);

/** Код крупно, как в устройстве: несовпадение должно бросаться в глаза. */
export const DeviceCodeDisplay = ({
  code,
  title,
  hint,
  testId,
}: {
  code: string;
  title: string;
  hint: string;
  testId: string;
}) => (
  <div
    className="flex flex-col"
    style={{
      gap: 4,
      padding: "12px 14px",
      borderRadius: "var(--r-2)",
      border: "1px solid var(--accent)",
      background: "var(--bg-0)",
    }}
  >
    <span className="dim" style={{ fontSize: 12 }}>
      {title}
    </span>
    <span
      className="mono"
      style={{
        fontSize: 28,
        fontWeight: 600,
        letterSpacing: "0.14em",
        color: "var(--fg-0)",
      }}
      data-testid={testId}
    >
      {code}
    </span>
    <span className="dim" style={{ fontSize: 12 }}>
      {hint}
    </span>
  </div>
);

/** Сведения об устройстве: подпись слева, значение справа. */
export const DeviceFacts = ({ children }: { children: ReactNode }) => (
  <dl
    style={{
      display: "grid",
      gridTemplateColumns: "max-content 1fr",
      gap: "8px 16px",
      margin: 0,
      fontSize: 13,
    }}
  >
    {children}
  </dl>
);

export const DeviceFact = ({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) => (
  <>
    <dt style={{ color: "var(--fg-2)" }}>{label}</dt>
    <dd style={{ margin: 0, color: "var(--fg-0)", overflowWrap: "anywhere" }}>
      {children}
    </dd>
  </>
);

export type DeviceResultTone = "good" | "neutral" | "denied" | "warn";

const TONE_COLOR: Record<DeviceResultTone, string> = {
  good: "var(--c-ok)",
  neutral: "var(--fg-2)",
  denied: "var(--fg-2)",
  warn: "var(--c-warn)",
};

/** Итог: значок, заголовок, пояснение и действия; объявляется программам чтения. */
export const DeviceResult = ({
  tone,
  title,
  body,
  actions,
  testId,
  state,
}: {
  tone: DeviceResultTone;
  title: string;
  body: string;
  actions?: ReactNode;
  testId: string;
  state: string;
}) => {
  const Icon =
    tone === "good" ? CircleCheck : tone === "denied" ? CircleX : CircleAlert;
  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      role="status"
      aria-live="polite"
      data-testid={testId}
      data-state={state}
    >
      <div className="flex items-start" style={{ gap: 12 }}>
        <Icon
          size={22}
          aria-hidden="true"
          style={{ color: TONE_COLOR[tone], flexShrink: 0 }}
        />
        <div className="flex flex-col" style={{ gap: 4 }}>
          <h1 style={{ margin: 0, fontSize: 18 }}>{title}</h1>
          <p
            className="dim"
            style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}
          >
            {body}
          </p>
        </div>
      </div>
      {actions && (
        <div
          className="flex items-center"
          style={{ gap: 8, justifyContent: "flex-end" }}
        >
          {actions}
        </div>
      )}
    </div>
  );
};
