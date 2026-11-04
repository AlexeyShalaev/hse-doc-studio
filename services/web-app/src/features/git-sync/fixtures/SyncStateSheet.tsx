import { useMemo, useState } from "react";
import { Popover } from "@shared/ui/Popover";
import { SyncStatusSegmentView } from "../ui/SyncStatusSegment";
import { ConflictBannerView } from "../ui/ConflictBanner";
import { SyncButton } from "../ui/SyncButton";
import { SyncPanelView } from "../ui/SyncPanelView";
import { SyncPopover } from "../ui/SyncPopover";
import { deriveSyncUi } from "../model/syncUi.model";
import { useSyncText } from "../model/useSyncText";
import type { SyncStateFixture } from "./syncStates";

const noop = (): void => undefined;

const label = {
  fontSize: "0.65625rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase" as const,
  color: "var(--fg-3)",
  marginBottom: 6,
};

const Slot = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <div style={{ minWidth: 0 }}>
    <div style={label}>{title}</div>
    {children}
  </div>
);

// Такое состояние видно в нескольких местах сразу: кнопка в заголовке, панель
// под ней, сегмент строки состояния, полоса конфликтов и бейдж рейки. Лист
// показывает их вместе, как в окне проекта, но из готовых данных.
export const SyncStateSheet = ({ fixture }: { fixture: SyncStateFixture }) => {
  const [now] = useState(() => Date.now());
  const status = useMemo(() => fixture.build(now), [fixture, now]);
  const ui = useMemo(
    () =>
      deriveSyncUi(status, {
        online: fixture.context?.online ?? true,
        readOnly: fixture.context?.readOnly ?? false,
      }),
    [fixture, status],
  );
  const text = useSyncText(ui, now);
  const [open, setOpen] = useState(false);

  if (!ui.visible) return null;

  return (
    <div className="flex flex-col" style={{ gap: "1rem" }}>
      <div className="flex flex-wrap items-start" style={{ gap: "1.5rem" }}>
        <Slot title="Кнопка в заголовке">
          <Popover open={false}>
            <SyncButton
              ui={ui}
              text={text}
              isOpen={open}
              onPrimary={noop}
              onToggleDetails={() => {
                setOpen((value) => !value);
              }}
            />
          </Popover>
        </Slot>
        <Slot title="Строка состояния">
          <div
            className="flex items-center"
            style={{
              padding: "0.25rem 0.625rem",
              borderRadius: "0.375rem",
              border: "1px solid var(--border)",
              background: "var(--bg-2)",
              fontSize: "0.71875rem",
            }}
          >
            <SyncStatusSegmentView
              ui={ui}
              status={status}
              text={text}
              isOpen={false}
              onToggle={noop}
            />
          </div>
        </Slot>
        <Slot title="Бейдж на рейке «История»">
          {ui.railBadge ? (
            <span
              className="tnum"
              style={{
                display: "inline-flex",
                minWidth: "1.125rem",
                height: "1.125rem",
                padding: "0 0.3125rem",
                borderRadius: "0.5625rem",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.6875rem",
                fontWeight: 600,
                color: "var(--bg-0)",
                background: `var(--c-${ui.railBadge.tone})`,
              }}
            >
              {ui.railBadge.count}
            </span>
          ) : (
            <span className="dim" style={{ fontSize: "0.75rem" }}>
              нет
            </span>
          )}
        </Slot>
      </div>

      {fixture.banner && status.pending && (
        <Slot title="Полоса вверху экрана">
          <ConflictBannerView
            open={status.pending.files_open}
            total={status.pending.files_total}
            onOpen={noop}
          />
        </Slot>
      )}

      <div className="flex flex-wrap items-start" style={{ gap: "1.5rem" }}>
        <Slot title="Панель под кнопкой">
          <div
            className="overflow-hidden rounded-r-3 border border-border bg-bg-1 shadow-elev-pop"
            style={{ width: "25rem", maxWidth: "100%" }}
          >
            <SyncPopover
              ui={ui}
              status={status}
              text={text}
              now={now}
              isStarting={false}
              isChecking={false}
              isCancelling={false}
              onSync={noop}
              onCheck={noop}
              onCancel={noop}
              onConnect={noop}
              onFixAccess={noop}
              onResolve={noop}
              onOpenSettings={noop}
              onOpenHistory={noop}
              onOpenProfile={noop}
            />
          </div>
        </Slot>
        <Slot title="Панель на странице «Версии»">
          <div
            className="rounded-r-3 border border-border bg-bg-1"
            style={{ width: "28.75rem", maxWidth: "100%", padding: "0.875rem" }}
          >
            <SyncPanelView
              ui={ui}
              status={status}
              text={text}
              now={now}
              isStarting={false}
              isChecking={false}
              isCancelling={false}
              onSync={noop}
              onCheck={noop}
              onCancel={noop}
              onConnect={noop}
              onBundle={noop}
              onFixAccess={noop}
              onResolve={noop}
              onOpenSettings={noop}
              onOpenProfile={noop}
              onAcknowledgeSharedFolder={noop}
              onShowInHistory={noop}
              selectedIncomingId={null}
              onSelectIncoming={noop}
            />
          </div>
        </Slot>
      </div>
    </div>
  );
};
