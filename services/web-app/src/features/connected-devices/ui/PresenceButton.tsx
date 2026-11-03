import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { PopoverAnchor, PopoverTrigger } from "@shared/ui/Popover";
import { StatusDot } from "@shared/ui/StatusDot";
import type { PresenceSummary } from "../model/summary";

const DOT = {
  ok: "online",
  info: "info",
  warn: "warning",
  err: "danger",
  quiet: "offline",
} as const;

export type PresenceButtonProps = {
  summary: PresenceSummary;
  isOpen: boolean;
};

/**
 * Плашка присутствия в заголовке окна: цветная точка и подпись, стрелка открывает панель подробностей. Внешний
 * вид тот же, что у кнопки синхронизации, чтобы заголовок не пестрел разными элементами.
 */
export const PresenceButton = ({ summary, isOpen }: PresenceButtonProps) => {
  const { t } = useTranslation("devices");
  return (
    <PopoverAnchor asChild>
      <div
        className="sync-control studio-presence"
        data-tone={summary.tone === "quiet" ? undefined : summary.tone}
        data-open={isOpen ? "true" : undefined}
        data-testid="studio-presence"
        data-online={summary.online ? "true" : "false"}
      >
        <PopoverTrigger asChild>
          <button
            type="button"
            className="sync-main"
            data-studio-trigger
            aria-label={t("badge.aria", { summary: summary.title })}
            title={summary.title}
          >
            <StatusDot status={DOT[summary.tone]} label={summary.label} />
            <ChevronDown
              size={12}
              aria-hidden="true"
              style={{ color: "var(--fg-2)" }}
            />
          </button>
        </PopoverTrigger>
      </div>
    </PopoverAnchor>
  );
};
