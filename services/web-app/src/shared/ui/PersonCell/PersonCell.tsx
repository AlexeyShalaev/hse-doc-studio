import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { initialsOf } from "../../lib/initialsOf";

// Человек в таблицах и журналах: аватар с инициалами, имя, почта. Сырой
// идентификатор на экран не выводится: если о человеке известен только id,
// показываем нейтральную подпись, а id остаётся в подсказке.

const PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
] as const;

const colorFor = (seed: string): string => {
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length] ?? PALETTE[0];
};

export type AvatarProps = {
  /** Имя для инициалов; пусто — «?». */
  name?: string | null | undefined;
  /** Строка для цвета: id или почта, чтобы цвет не менялся при смене имени. */
  seed?: string | null | undefined;
  size?: number | undefined;
  /** Свои инициалы вместо вычисленных. */
  initials?: string | undefined;
};

export const Avatar = ({ name, seed, size = 24, initials }: AvatarProps) => {
  const text = initials ?? (name ? initialsOf(name) : "?");
  const known = Boolean(name ?? initials);
  const style: CSSProperties & Record<"--adm-av", string> = {
    width: size,
    height: size,
    fontSize: Math.max(9, Math.round(size * 0.4)),
    "--adm-av": known ? colorFor(seed ?? name ?? "") : "var(--fg-3)",
  };
  return (
    <span className="adm-avatar" aria-hidden="true" style={style}>
      {text}
    </span>
  );
};

export type PersonCellProps = {
  name?: string | null | undefined;
  email?: string | null | undefined;
  /** Идентификатор: только для цвета и подсказки, на экран не выводится. */
  id?: string | null | undefined;
  /** Вторая строка вместо почты (роль, «вы»). */
  subtitle?: ReactNode | undefined;
  /** Подпись, когда о человеке ничего не известно. */
  fallback?: string | undefined;
  /** sm: аватар 20 px и одна строка; md: аватар 28 px и две строки. */
  size?: "sm" | "md" | undefined;
  /** Метки после имени (роль, «админ»). */
  badges?: ReactNode | undefined;
  testId?: string | undefined;
};

export const PersonCell = ({
  name,
  email,
  id,
  subtitle,
  fallback,
  size = "md",
  badges,
  testId,
}: PersonCellProps) => {
  const { t } = useTranslation("uiPrimitives");
  const clean = (value: string | null | undefined): string | null => {
    const text = value?.trim() ?? "";
    return text === "" ? null : text;
  };
  const title = clean(name) ?? clean(email);
  const unknown = title === null;
  const shown = title ?? fallback ?? t("adminKit.person.unknown");
  const second = subtitle ?? (clean(name) && email ? email : null);
  const tip = [name, email, unknown ? id : null].filter(Boolean).join(" · ");
  return (
    <span className="adm-person" title={tip || undefined} data-testid={testId}>
      <Avatar
        name={unknown ? null : shown}
        seed={id ?? email ?? name ?? null}
        size={size === "sm" ? 20 : 28}
      />
      <span className="adm-person-text">
        <span className="flex items-center" style={{ gap: 6, minWidth: 0 }}>
          <span
            className="adm-person-name"
            data-unknown={unknown ? "true" : undefined}
          >
            {shown}
          </span>
          {badges}
        </span>
        {size === "md" && second && (
          <span className="adm-person-sub">{second}</span>
        )}
      </span>
    </span>
  );
};

Avatar.displayName = "Avatar";
PersonCell.displayName = "PersonCell";
