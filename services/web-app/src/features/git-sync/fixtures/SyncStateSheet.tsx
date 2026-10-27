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
  fontSize: 10.5,
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
    <div className="flex flex-col" style={{ gap: 16 }}>
      <div className="flex flex-wrap items-start" style={{ gap: 24 }}>
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
              padding: "4px 10px",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--bg-2)",
              fontSize: 11.5,
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
                minWidth: 18,
                height: 18,
                padding: "0 5px",
                borderRadius: 9,
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11,
                fontWeight: 600,
                color: "var(--bg-0)",
                background: `var(--c-${ui.railBadge.tone})`,
              }}
            >
              {ui.railBadge.count}
            </span>
          ) : (
            <span className="dim" style={{ fontSize: 12 }}>
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

      <div className="flex flex-wrap items-start" style={{ gap: 24 }}>
        <Slot title="Панель под кнопкой">
          <div
            className="overflow-hidden rounded-r-3 border border-border bg-bg-1 shadow-elev-pop"
            style={{ width: 400, maxWidth: "100%" }}
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
            style={{ width: 460, maxWidth: "100%", padding: 14 }}
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
