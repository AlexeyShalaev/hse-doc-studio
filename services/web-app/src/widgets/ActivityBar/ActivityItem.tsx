import { clsx } from "clsx";
import type { LucideIcon } from "lucide-react";

// Иконки бара крупнее строчных (13px в списках документов): 56-пиксельная
// колонка — цель для беглого клика, а не элемент плотного списка.
const ICON_SIZE = 17;

// Выше сотни точная цифра уже ничего не решает («много ошибок» и «очень
// много ошибок» ведут в одно и то же место), а третий символ ломает
// 15-пиксельный кружок бейджа.
const MAX_BADGE_COUNT = 99;

export type ActivityBadgeTone = "err" | "warn" | "info";

// Бейдж либо считает проблемы, либо пульсирует, пока идёт сборка. Живой
// вариант несёт свою подпись: сам ActivityItem остаётся презентационным и не
// знает про i18n — строки приходят сверху вместе с остальными подписями.
export type ActivityItemBadge =
  | { kind: "live"; label: string }
  | { kind: "count"; tone: ActivityBadgeTone; count: number };

export type ActivityItemProps = {
  icon: LucideIcon;
  label: string;
  // Развёрнутая подсказка. Подпись под иконкой уже называет режим, поэтому
  // тултип — нативный `title`: он уточняет, а не подменяет имя кнопки, и не
  // тянет за собой портал ради шести статичных строк.
  tooltip: string;
  isActive: boolean;
  onSelect: () => void;
  badge?: ActivityItemBadge | undefined;
};

const formatBadgeCount = (count: number): string =>
  count > MAX_BADGE_COUNT ? `${String(MAX_BADGE_COUNT)}+` : String(count);

export const ActivityItem = ({
  icon: Icon,
  label,
  tooltip,
  isActive,
  onSelect,
  badge,
}: ActivityItemProps): React.JSX.Element => (
  <button
    type="button"
    className={clsx("activity-item", isActive && "active")}
    title={tooltip}
    aria-current={isActive ? "page" : undefined}
    onClick={onSelect}
  >
    <Icon size={ICON_SIZE} aria-hidden />
    <span className="activity-item-label">{label}</span>
    {badge?.kind === "live" && (
      // role="img" делает aria-label легальным на пустом span: без роли
      // подпись у generic-элемента скринридеры вправе проигнорировать.
      <span
        className="activity-badge live"
        role="img"
        aria-label={badge.label}
      />
    )}
    {badge?.kind === "count" && (
      <span className={clsx("activity-badge", badge.tone)}>
        {formatBadgeCount(badge.count)}
      </span>
    )}
  </button>
);
