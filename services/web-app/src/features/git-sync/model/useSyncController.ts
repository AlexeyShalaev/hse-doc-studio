import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  describeGitError,
  gitConflictsPath,
  gitErrorMessage,
  gitHistoryPath,
  gitSyncKeys,
  invalidateAfterSync,
  readGitError,
  useCancelOperation,
  useFetchRemote,
  useOperation,
  useStartSync,
  useSyncUiStore,
  type GitOperation,
  type SyncResult,
} from "@entities/git-sync";
import { flushPendingSaves, toast } from "@shared/lib";
import type { SyncPrimaryAction } from "./syncUi.model";
import { useSyncView, type SyncView } from "./useSyncView";

// Итог считается «свежим» в течение этого времени: старую синхронизацию,
// найденную при открытии проекта, тостом не поднимаем.
const FRESH_SYNC_MS = 2 * 60_000;

// Запись last_sync после показанного итога приходит с очередным опросом состояния.
const EXPECT_RECORD_MS = 30_000;

const isSyncResult = (
  result: GitOperation["result"] | undefined,
): result is SyncResult =>
  !!result && typeof (result as { outcome?: unknown }).outcome === "string";

export type SyncController = SyncView & {
  /** Операция, за которой следит экран (запущена здесь, в другой вкладке или до перезагрузки). */
  operation: GitOperation | undefined;
  isStarting: boolean;
  isChecking: boolean;
  isCancelling: boolean;
  run: () => Promise<void>;
  check: () => Promise<void>;
  cancel: () => void;
  /** То, что делает щелчок по основной части элемента. */
  runPrimary: (primary: SyncPrimaryAction) => void;
  openConflicts: () => void;
};

/**
 * Запуск и сопровождение синхронизации: сначала дописывает несохранённые правки
 * редакторов, потом просит сервер, потом следит за операцией и один раз
 * сообщает итог. Опираться на «я сам нажал» нельзя: операцию могут начать в
 * другой вкладке или до перезагрузки страницы, поэтому за ней следим по
 * состоянию проекта.
 */
export const useSyncController = (projectId: string): SyncController => {
  const { t } = useTranslation("gitSync");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const view = useSyncView(projectId);
  const { status, ui } = view;

  const startSync = useStartSync();
  const fetchRemote = useFetchRemote();
  const cancelOperation = useCancelOperation();

  // Операция, запущенная отсюда: её видно сразу, до того как состояние проекта
  // узнает о ней. Состояние проекта приоритетнее: пока там идёт другая операция,
  // следим за ней.
  const [startedId, setStartedId] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const trackedId = status?.operation?.id ?? startedId;
  const { data: operation } = useOperation(trackedId);

  const startingRef = useRef(false);
  const startedHere = useRef(new Set<string>());
  const handled = useRef(new Set<string>());
  // Когда итог показан по операции: новую запись last_sync, что появится в
  // состоянии следом, «погасим» без второго тоста.
  const expectSyncRecordAt = useRef(0);

  const openConflicts = useCallback((): void => {
    void navigate(gitConflictsPath(projectId));
  }, [navigate, projectId]);

  const openPopover = useCallback((): void => {
    useSyncUiStore.getState().setPopoverOpen(true);
  }, []);

  // --- итог операции -----------------------------------------------------------

  const announceFinished = useCallback(
    (op: GitOperation, mine: boolean): void => {
      if (op.status === "failed") {
        const message = op.error
          ? gitErrorMessage(op.error.code, op.error.detail)
          : t("toast.failedUnknown");
        toast.error(message, {
          title: t("toast.failedTitle"),
          duration: 10_000,
          action: { label: t("toast.details"), onClick: openPopover },
        });
        return;
      }
      if (op.status === "cancelled") {
        toast.info(t("toast.cancelled"));
        return;
      }
      if (!isSyncResult(op.result)) return;
      const result = op.result;

      if (result.outcome === "conflicts") {
        const count = result.conflicts?.files_open ?? 0;
        toast.warning(t("toast.conflicts", { count }), {
          title: t("toast.conflictsTitle"),
          // Конфликт не исчезает сам: уведомление остаётся, пока его не закроют.
          duration: 0,
          action: { label: t("toast.resolve"), onClick: openConflicts },
        });
        // Только тому, кто сам запустил: чужой экран из-под рук не уводим.
        if (mine) openConflicts();
        return;
      }

      expectSyncRecordAt.current = Date.now();
      const auto = result.auto.length;
      const base = ((): string => {
        switch (result.outcome) {
          case "up_to_date":
            return t("toast.up_to_date");
          case "pushed":
            return t("toast.pushed", { count: result.pushed_commits });
          case "fast_forwarded":
            return t("toast.fast_forwarded", { count: result.pulled_commits });
          default:
            return t("toast.merged", {
              pulled: result.pulled_commits,
              pushed: result.pushed_commits,
            });
        }
      })();
      const message =
        auto > 0 ? `${base}. ${t("toast.auto", { count: auto })}` : base;
      toast.success(message, {
        title: t("toast.syncedTitle"),
        ...(result.outcome === "up_to_date"
          ? {}
          : {
              action: {
                label: t("toast.openHistory"),
                onClick: () => {
                  void navigate(gitHistoryPath(projectId));
                },
              },
            }),
      });
      if (result.warnings.length > 0) {
        const list = result.warnings
          .map((w) => t(`warning.${w.code}`, { defaultValue: w.code }))
          .join("; ");
        toast.warning(t("toast.warnings", { list }), { duration: 10_000 });
      }
    },
    [navigate, openConflicts, openPopover, projectId, t],
  );

  // Следим за кэшем операций, а не за состоянием компонента: итог надо показать
  // ровно один раз, а перерисовок и повторных чтений операции много.
  useEffect(() => {
    const cache = queryClient.getQueryCache();
    return cache.subscribe((event) => {
      if (event.type !== "updated") return;
      const key = event.query.queryKey as readonly unknown[];
      if (key[0] !== gitSyncKeys.all[0] || key[1] !== "operation") return;
      const op = event.query.state.data as GitOperation | undefined;
      if (!op || op.status === "running") return;
      // Клон и импорт архива живут в своих экранах; чужие проекты не трогаем.
      if (op.kind !== "sync" && op.kind !== "resolve") return;
      if (op.project_id !== projectId) return;
      if (handled.current.has(op.id)) return;
      handled.current.add(op.id);
      announceFinished(op, startedHere.current.has(op.id));
      // Слияние поменяло файлы, версии, подписи и формы.
      invalidateAfterSync(queryClient, projectId);
    });
  }, [announceFinished, projectId, queryClient]);

  // Операция закончилась, пока страница была закрыта (или в другой вкладке и без
  // нашего наблюдения): сервер помнит итог в last_sync, показываем его один раз.
  const lastSync = status?.last_sync ?? null;
  const isOperationActive = !!status?.operation;
  useEffect(() => {
    if (!lastSync || isOperationActive) return;
    if (startingRef.current) return;
    const store = useSyncUiStore.getState();
    if (!store.claimSyncToast(projectId, lastSync.id)) return;
    // Конфликт уже показан состоянием проекта, баннером и тостом операции.
    if (lastSync.outcome === "conflicts") return;
    // Операцию запустили здесь, а её итог ещё не показан: опрос состояния
    // обогнал опрос операции, подробный тост даст она.
    for (const id of startedHere.current) {
      if (!handled.current.has(id)) return;
    }
    if (Date.now() - expectSyncRecordAt.current < EXPECT_RECORD_MS) {
      expectSyncRecordAt.current = 0;
      return;
    }
    if (Date.now() - Date.parse(lastSync.at) > FRESH_SYNC_MS) return;
    toast.success(
      lastSync.outcome === "up_to_date"
        ? t("toast.up_to_date")
        : t("toast.merged", {
            pulled: lastSync.pulled_commits,
            pushed: lastSync.pushed_commits,
          }),
      { title: t("toast.syncedTitle") },
    );
  }, [isOperationActive, lastSync, projectId, t]);

  // --- действия ----------------------------------------------------------------

  const run = useCallback(async (): Promise<void> => {
    if (startingRef.current) return;
    startingRef.current = true;
    setIsStarting(true);
    try {
      // Правки в редакторах дописываются с задержкой; снимок без них вышел бы
      // неполным, а сами они потом легли бы поверх слитых файлов.
      const flushed = await flushPendingSaves();
      if (flushed.failed > 0) {
        toast.error(t("toast.saveFailed"), {
          title: t("toast.saveFailedTitle"),
          duration: 10_000,
        });
        return;
      }
      const { operation_id: operationId } =
        await startSync.mutateAsync(projectId);
      startedHere.current.add(operationId);
      setStartedId(operationId);
    } catch (error) {
      const body = readGitError(error);
      if (body?.code === "sync_busy" && body.operation_id) {
        // Уже идёт: подключаемся к ней, как будто сами запустили.
        startedHere.current.add(body.operation_id);
        setStartedId(body.operation_id);
        return;
      }
      toast.error(describeGitError(error, t("toast.failedUnknown")), {
        title: t("toast.startFailedTitle"),
      });
    } finally {
      startingRef.current = false;
      setIsStarting(false);
    }
  }, [projectId, startSync, t]);

  const check = useCallback(async (): Promise<void> => {
    try {
      const fresh = await fetchRemote.mutateAsync(projectId);
      if (fresh.behind > 0) {
        toast.info(t("toast.checkFound", { count: fresh.behind }));
      } else {
        toast.success(t("toast.checkNone"));
      }
    } catch (error) {
      toast.error(describeGitError(error, t("toast.failedUnknown")), {
        title: t("toast.checkFailedTitle"),
      });
    }
  }, [fetchRemote, projectId, t]);

  const cancel = useCallback((): void => {
    const id = status?.operation?.id ?? trackedId;
    if (!id) return;
    cancelOperation.mutate(id, {
      onError: (error) => {
        toast.error(describeGitError(error, t("toast.failedUnknown")));
      },
    });
  }, [cancelOperation, status?.operation?.id, t, trackedId]);

  const runPrimary = useCallback(
    (primary: SyncPrimaryAction): void => {
      const store = useSyncUiStore.getState();
      switch (primary) {
        case "connect":
          store.openConnectDialog("connect");
          return;
        case "fix_access":
          store.openConnectDialog("fix_access");
          return;
        case "sync":
          void run();
          return;
        case "retry":
          void check();
          return;
        case "resolve":
          openConflicts();
          return;
        default:
          openPopover();
      }
    },
    [check, openConflicts, openPopover, run],
  );

  // --- команды из палитры и сочетания клавиш -------------------------------------

  const command = useSyncUiStore((state) => state.command);
  useEffect(() => {
    if (!command) return;
    useSyncUiStore.getState().consumeCommand(command.id);
    if (!ui.visible) return;
    // Команда пришла снаружи (палитра, клавиши), а выполнение меняет состояние
    // экрана: откладываем его из тела эффекта.
    queueMicrotask(() => {
      if (command.kind === "run") {
        if (ui.canSync) void run();
        else openPopover();
        return;
      }
      if (command.kind === "check") {
        if (ui.canCheck) void check();
        else openPopover();
        return;
      }
      runPrimary(ui.primary);
    });
  }, [check, command, openPopover, run, runPrimary, ui]);

  return {
    ...view,
    operation,
    isStarting,
    isChecking: fetchRemote.isPending,
    isCancelling: cancelOperation.isPending,
    run,
    check,
    cancel,
    runPrimary,
    openConflicts,
  };
};
