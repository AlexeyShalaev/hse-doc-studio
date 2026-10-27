import { ArrowDown, ArrowUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSyncUiStore, type SyncStatusView } from "@entities/git-sync";
import type { SyncTone, SyncUi } from "../model/syncUi.model";
import { useNowTick } from "../model/useNowTick";
import { useSyncText, type SyncText } from "../model/useSyncText";
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

export type SyncStatusSegmentViewProps = {
  ui: SyncUi;
  status: SyncStatusView;
  text: SyncText;
  isOpen: boolean;
  onToggle: () => void;
};

/**
 * Сегмент строки состояния: «git · ветка, числа». Только вид: данные и
 * действие приходят снаружи, поэтому каждое состояние можно показать в тесте и
 * в галерее состояний.
 */
export const SyncStatusSegmentView = ({
  ui,
  status,
  text,
  isOpen,
  onToggle,
}: SyncStatusSegmentViewProps) => {
  const { t } = useTranslation("gitSync");
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
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onToggle();
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

/**
 * Сегмент строки состояния проекта: данные берёт из общего запроса состояния,
 * щелчок открывает панель подробностей в заголовке окна. Доступен с клавиатуры,
 * как соседние сегменты.
 */
export const SyncStatusSegment = ({ projectId }: SyncStatusSegmentProps) => {
  const { status, ui } = useSyncView(projectId);
  const now = useNowTick();
  const text = useSyncText(ui, now);
  const toggle = useSyncUiStore((state) => state.togglePopover);
  const isOpen = useSyncUiStore((state) => state.popoverOpen);

  if (!status || !ui.visible) return null;
  return (
    <SyncStatusSegmentView
      ui={ui}
      status={status}
      text={text}
      isOpen={isOpen}
      onToggle={toggle}
    />
  );
};
