import { ArrowDown, ArrowUp, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { PopoverAnchor, PopoverTrigger } from "@shared/ui/Popover";
import type { SyncUi } from "../model/syncUi.model";
import type { SyncText } from "../model/useSyncText";
import { SyncStateIcon } from "./SyncStateIcon";

export type SyncButtonProps = {
  ui: SyncUi;
  text: SyncText;
  /** Открыта ли панель подробностей. */
  isOpen: boolean;
  /** Щелчок по основной части: действие по состоянию (синхронизировать, решить...). */
  onPrimary: () => void;
  /** Правый щелчок и долгое нажатие открывают панель, как стрелка справа. */
  onToggleDetails: () => void;
};

const Counts = ({ ui }: { ui: SyncUi }) => {
  if (ui.state === "conflicts") {
    return ui.conflictFiles > 0 ? (
      <span className="sync-count" aria-hidden="true">
        {ui.conflictFiles}
      </span>
    ) : null;
  }
  if (ui.state === "syncing") {
    return ui.percent === null ? null : (
      <span className="sync-count" aria-hidden="true">
        {Math.round(ui.percent)}%
      </span>
    );
  }
  if (
    ui.state !== "ahead" &&
    ui.state !== "behind" &&
    ui.state !== "diverged"
  ) {
    return null;
  }
  return (
    <>
      {ui.incoming > 0 && (
        <span className="sync-count" aria-hidden="true">
          <ArrowDown size={10} strokeWidth={2.4} />
          {ui.incoming}
        </span>
      )}
      {ui.outgoing > 0 && (
        <span className="sync-count" aria-hidden="true">
          <ArrowUp size={10} strokeWidth={2.4} />
          {ui.outgoing}
        </span>
      )}
    </>
  );
};

/**
 * Кнопка синхронизации в заголовке окна: значок, подпись и числа, справа стрелка
 * подробностей. Состояние читается без цвета (значок и слова), цвет лишь
 * подчёркивает его. Должна лежать внутри `Popover`: она же его якорь и спуск.
 */
export const SyncButton = ({
  ui,
  text,
  isOpen,
  onPrimary,
  onToggleDetails,
}: SyncButtonProps) => {
  const { t } = useTranslation("gitSync");
  const name = t("control.name", { status: text.status, action: text.action });
  const showWhen = ui.state === "up_to_date" && text.when !== "";

  return (
    <PopoverAnchor asChild>
      <div
        className="sync-control"
        data-tone={ui.tone}
        data-state={ui.state}
        data-quiet={ui.state === "no_remote" ? "true" : undefined}
        data-open={isOpen ? "true" : undefined}
      >
        <button
          type="button"
          className="sync-main"
          data-sync-trigger
          aria-label={name}
          aria-busy={ui.busy || undefined}
          title={`${text.status}. ${text.action}`}
          onClick={onPrimary}
          onContextMenu={(event) => {
            event.preventDefault();
            onToggleDetails();
          }}
        >
          <span className="sync-icon">
            <SyncStateIcon icon={ui.icon} />
          </span>
          <span className="sync-label" aria-hidden="true">
            {text.label}
          </span>
          {showWhen && (
            <span className="sync-when" aria-hidden="true">
              {text.when}
            </span>
          )}
          <Counts ui={ui} />
        </button>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="sync-chevron"
            data-sync-trigger
            aria-label={t("control.details")}
            title={t("control.details")}
          >
            <ChevronDown size={13} aria-hidden="true" />
          </button>
        </PopoverTrigger>
      </div>
    </PopoverAnchor>
  );
};

/** Заглушка на время первого ответа: место занято, и заголовок не «прыгает». */
export const SyncButtonSkeleton = () => (
  <span className="sync-control sync-control-skeleton" aria-hidden="true" />
);
