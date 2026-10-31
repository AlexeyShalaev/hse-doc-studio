import { useCallback, useEffect, useRef, useState } from "react";
import { useUpdateGitSettings } from "@entities/git-sync";
import { useProjectLastEdit } from "@shared/lib";
import {
  autoSyncPhase,
  autoSyncWork,
  decideAutoSync,
  type AutoSyncFacts,
  type AutoSyncPhase,
  type AutoSyncStop,
} from "./autoSync.model";
import type { AutoRunResult, AutoStart } from "./useSyncController";
import type { SyncView } from "./useSyncView";

export type AutoSyncRunner = {
  start: () => Promise<AutoStart>;
  result: AutoRunResult | null;
};

/** Что видит человек про автосинхронизацию проекта и чем он ею управляет. */
export type AutoSyncInfo = {
  /** Проект подключён, и этот клиент может его синхронизировать. */
  available: boolean;
  enabled: boolean;
  /** Выбор сделал человек (иначе это умолчание для сервера Студии). */
  explicit: boolean;
  phase: AutoSyncPhase;
  stop: AutoSyncStop | null;
  /** Неудачи подряд; с `AUTO_SYNC_MAX_FAILURES` автосинхронизация встаёт. */
  failures: number;
  isSaving: boolean;
  setEnabled: (next: boolean) => void;
};

type AutoSyncView = Pick<SyncView, "status" | "ui" | "online" | "readOnly">;

/**
 * Автосинхронизация окна проекта (docs/design/local-sync.md, раздел 1): после
 * паузы в правках отправляет проект на сервер, при чужих изменениях без своих
 * правок забирает их; при конфликте, потере доступа, чужой ветке и т. п. встаёт и
 * ждёт человека. Решает чистая `decideAutoSync`, хук подаёт ей факты, держит
 * таймер и запускает синхронизацию через контроллер. Счёт неудач ведёт контроллер:
 * он видит исход каждой операции.
 */
export const useAutoSync = (
  projectId: string,
  view: AutoSyncView,
  runner: AutoSyncRunner,
): AutoSyncInfo => {
  const { status, ui, online, readOnly } = view;
  const update = useUpdateGitSettings();
  const lastEditAt = useProjectLastEdit(projectId);

  const connected = !!status?.supported && status.connected;
  const enabled = connected && (status.auto_sync.enabled ?? false);
  const ahead = status?.ahead ?? 0;
  const behind = status?.behind ?? 0;
  const lastSyncId = status?.last_sync?.id ?? null;
  const operationStartedAt = status?.operation?.started_at ?? null;

  const [tick, setTick] = useState(0);
  const [lastRunAt, setLastRunAt] = useState<number | null>(null);
  // Неудачи до этого момента забыты: человек переключил автосинхронизацию.
  const [forgiveBefore, setForgiveBefore] = useState(0);
  const [seenSyncId, setSeenSyncId] = useState(lastSyncId);
  const [operationStart, setOperationStart] = useState<number | null>(null);
  const startRef = useRef(runner.start);
  const inFlight = useRef(false);
  const needSince = useRef<number | null>(null);

  useEffect(() => {
    startRef.current = runner.start;
  }, [runner.start]);

  // Начало идущей операции: правка после него снимком могла не попасть.
  if (operationStartedAt !== null && operationStart === null) {
    setOperationStart(Date.parse(operationStartedAt));
  }
  // Любая закончившаяся синхронизация (в том числе ручная) покрывает правки до своего начала.
  if (seenSyncId !== lastSyncId) {
    setSeenSyncId(lastSyncId);
    if (operationStart !== null) {
      setLastRunAt((prev) => Math.max(prev ?? 0, operationStart));
    }
    setOperationStart(null);
  }

  const result = runner.result;
  const counted = result !== null && result.at > forgiveBefore;
  const failures = counted && !result.ok ? result.failures : 0;
  const lastFailureAt = counted && !result.ok ? result.at : null;

  const facts: Omit<AutoSyncFacts, "now" | "needSince"> = {
    enabled,
    readOnly,
    online,
    state: ui.state,
    ahead,
    behind,
    lastEditAt,
    lastRunAt,
    failures,
    lastFailureAt,
  };
  const work = autoSyncWork(facts);
  const { phase, stop } = autoSyncPhase(work, failures);

  // Исполнитель: время известно только здесь, поэтому решение принимается внутри эффекта.
  useEffect(() => {
    const now = Date.now();
    needSince.current = work.wants === null ? null : (needSince.current ?? now);
    const decision = decideAutoSync({
      enabled,
      readOnly,
      online,
      state: ui.state,
      ahead,
      behind,
      now,
      needSince: needSince.current ?? now,
      lastEditAt,
      lastRunAt,
      failures,
      lastFailureAt,
    });
    if (decision.kind === "wait") {
      const timer = window.setTimeout(
        () => {
          setTick((value) => value + 1);
        },
        Math.max(250, decision.delayMs),
      );
      return () => {
        window.clearTimeout(timer);
      };
    }
    if (decision.kind !== "run" || inFlight.current) return undefined;
    inFlight.current = true;
    void startRef.current().then(() => {
      // Зазор между запусками считается от начала, даже если запуск не вышел: сбой учтёт контроллер.
      setLastRunAt(now);
      inFlight.current = false;
    });
    return undefined;
  }, [
    tick,
    work.wants,
    enabled,
    readOnly,
    online,
    ui.state,
    ahead,
    behind,
    lastEditAt,
    lastRunAt,
    failures,
    lastFailureAt,
  ]);

  const setEnabled = useCallback(
    (next: boolean): void => {
      setForgiveBefore(Date.now());
      update.mutate({ projectId, params: { auto_sync: next } });
    },
    [projectId, update],
  );

  return {
    available: connected && !readOnly,
    enabled,
    explicit: status?.auto_sync.explicit ?? false,
    phase,
    stop,
    failures,
    isSaving: update.isPending,
    setEnabled,
  };
};
