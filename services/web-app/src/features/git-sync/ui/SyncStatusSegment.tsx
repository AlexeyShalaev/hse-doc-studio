import { ArrowDown, ArrowUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSyncUiStore } from "@entities/git-sync";
import type { SyncTone } from "../model/syncUi.model";
import { useNowTick } from "../model/useNowTick";
import { useSyncText } from "../model/useSyncText";
import { useSyncView } from "../model/useSyncView";

export type SyncStatusSegmentProps = {
  projectId: string;
};

const DOT: Record<SyncTone, string> = {
  muted: "dot pending",
  ok: "dot ok",
  info: "dot info",
  warn: "dot warn",
  err: "dot err",
  accent: "dot live",
};

// Состояния, о которых скажем словами: цвет точки в строке состояния слишком
// мал, чтобы нести смысл в одиночку.
const WORDED = new Set([
  "conflicts",
  "auth_failed",
  "offline",
  "error",
  "blocked",
  "unknown",
]);

/**
 * Сегмент строки состояния: «git · ветка, числа». Щелчок открывает панель
 * подробностей в заголовке окна. Доступен с клавиатуры, как соседние сегменты.
 */
export const SyncStatusSegment = ({ projectId }: SyncStatusSegmentProps) => {
  const { t } = useTranslation("gitSync");
  const { status, ui } = useSyncView(projectId);
  const now = useNowTick();
  const text = useSyncText(ui, now);
  const toggle = useSyncUiStore((state) => state.togglePopover);
  const isOpen = useSyncUiStore((state) => state.popoverOpen);

  if (!status || !ui.visible) return null;

  const branch = status.remote?.branch ?? "";
  const isConnected = status.connected;
  const dotClass = ui.state === "syncing" ? "dot building" : DOT[ui.tone];

  return (
    <span
      className="seg-item seg-clickable"
      role="button"
      tabIndex={0}
      data-sync-trigger
      aria-haspopup="dialog"
      aria-expanded={isOpen}
      aria-label={t("statusBar.name", { status: text.status })}
      title={`${text.status}. ${text.action}`}
      onClick={toggle}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggle();
        }
      }}
    >
      <span className={dotClass} aria-hidden="true" />
      <span aria-hidden="true">git</span>
      {isConnected ? (
        <>
          <span aria-hidden="true">
            {" · "}
            {ui.state === "syncing" ? text.label : branch}
          </span>
          {ui.state !== "syncing" && ui.incoming > 0 && (
            <span className="inline-flex items-center" aria-hidden="true">
              <ArrowDown size={10} strokeWidth={2.4} />
              {ui.incoming}
            </span>
          )}
          {ui.state !== "syncing" && ui.outgoing > 0 && (
            <span className="inline-flex items-center" aria-hidden="true">
              <ArrowUp size={10} strokeWidth={2.4} />
              {ui.outgoing}
            </span>
          )}
          {WORDED.has(ui.state) && (
            <span aria-hidden="true">
              {" · "}
              {text.label}
            </span>
          )}
        </>
      ) : (
        <span aria-hidden="true">
          {" · "}
          {t("statusBar.notConnected")}
        </span>
      )}
    </span>
  );
};
