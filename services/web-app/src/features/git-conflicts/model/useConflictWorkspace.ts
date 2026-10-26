import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  describeGitError,
  gitHistoryPath,
  gitSyncApi,
  gitSyncKeys,
  invalidateAfterSync,
  readGitError,
  useAbortConflicts,
  useCancelOperation,
  useConflictFile,
  useOperation,
  useResolveConflicts,
  useSyncStatus,
  type ConflictFile,
  type ConflictFileDetail,
  type ConflictSession,
  type GitOperation,
  type HunkChoice,
  type SyncResult,
} from "@entities/git-sync";
import { toast } from "@shared/lib";
import {
  carryOverDrafts,
  chooseAllHunks,
  clearHunkChoice,
  fileProgress,
  isTextDetail,
  needsDecision,
  nextOpenHunkKey,
  nextOpenPath,
  pruneResolution,
  sessionProgress,
  setFileChoice,
  setHunkChoice,
  setManualText,
  type DraftMap,
  type FileProgress,
  type SessionProgress,
} from "./conflictModel";
import { useConflictDrafts, type ConflictDrafts } from "./useConflictDrafts";

export type ConflictView = "parts" | "mine" | "theirs" | "result" | "manual";

/** Что сказать пользователю над списком: единственное сообщение за раз. */
export type ConflictNotice =
  | { kind: "outdated" }
  | { kind: "restarted" }
  | { kind: "unresolved"; count: number }
  | { kind: "error"; message: string };

/** На каком шаге завершение. */
export type ConflictCompletion =
  | { kind: "idle" }
  | { kind: "running"; operation: GitOperation | null }
  | { kind: "done"; operation: GitOperation }
  | { kind: "failed"; operation: GitOperation }
  | { kind: "cancelled"; operation: GitOperation };

export type HunkFocusRequest = { key: string; token: number };

export type ConflictWorkspace = {
  session: ConflictSession;
  progress: SessionProgress;
  progressOf: (file: ConflictFile) => FileProgress;
  drafts: ConflictDrafts;
  /** Файлы, где нужно решение, и файлы, которые сервер решил сам. */
  needs: ConflictFile[];
  auto: ConflictFile[];
  selected: ConflictFile | null;
  selectFile: (path: string) => void;
  goNextOpenFile: () => void;
  view: ConflictView;
  setView: (view: ConflictView) => void;
  detail: ConflictFileDetail | undefined;
  detailLoading: boolean;
  detailError: boolean;
  reloadDetail: () => void;
  /** Место, на которое просят перевести фокус (после выбора, по N). */
  focusRequest: HunkFocusRequest | null;
  clearFocusRequest: (token: number) => void;
  activeHunk: string | null;
  setActiveHunk: (key: string) => void;
  jumpHunk: (direction: 1 | -1) => void;
  chooseHunk: (key: string, choice: HunkChoice) => void;
  clearHunk: (key: string) => void;
  chooseAll: (choice: "mine" | "theirs") => void;
  chooseFile: (choice: string) => void;
  applyManual: (content: string) => void;
  revertManual: () => void;
  canComplete: boolean;
  complete: () => Promise<void>;
  retryCompletion: () => Promise<void>;
  dismissCompletion: () => void;
  cancelCompletion: () => void;
  /** Слияние уже закоммичено, отправка не удалась: дальше только история. */
  openHistory: () => void;
  isCancelling: boolean;
  completion: ConflictCompletion;
  abort: () => Promise<void>;
  isAborting: boolean;
  notice: ConflictNotice | null;
  dismissNotice: () => void;
};

const isSyncResult = (
  result: GitOperation["result"] | undefined,
): result is SyncResult =>
  !!result && typeof (result as { outcome?: unknown }).outcome === "string";

/**
 * Всё, что делает экран конфликтов: выбор файла и вида, решения по местам,
 * сохранение черновиков, завершение (с повтором при «план устарел»), отмена
 * слияния. Само решение хранится в `useConflictDrafts`, а здесь оно связано с
 * выбранным файлом, фокусом и запросами.
 */
export const useConflictWorkspace = (
  projectId: string,
  session: ConflictSession,
): ConflictWorkspace => {
  const { t } = useTranslation("gitConflicts");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const drafts = useConflictDrafts(projectId, session);
  const {
    drafts: draftMap,
    update: updateDraft,
    replace: replaceDrafts,
    flush: flushDrafts,
    discard: discardDrafts,
  } = drafts;

  const progress = useMemo(
    () => sessionProgress(session, draftMap),
    [session, draftMap],
  );
  const progressOf = useCallback(
    (file: ConflictFile): FileProgress =>
      fileProgress(file, draftMap[file.path]),
    [draftMap],
  );

  const needs = useMemo(
    () => session.files.filter(needsDecision),
    [session.files],
  );
  const auto = useMemo(
    () => session.files.filter((f) => !needsDecision(f)),
    [session.files],
  );

  // --- выбранный файл и вид ---------------------------------------------------------

  // Начальный файл: первый нерешённый. Дальше его двигает только пользователь:
  // иначе файл «уезжал» бы из-под рук, как только его решили.
  const [selectedPath, setSelectedPath] = useState<string | null>(
    () => progress.openPaths[0] ?? needs[0]?.path ?? null,
  );
  const selected =
    session.files.find((f) => f.path === selectedPath) ??
    session.files.find((f) => f.path === progress.openPaths[0]) ??
    needs[0] ??
    session.files[0] ??
    null;
  const selectedKey = selected?.path ?? "";

  const [viewState, setViewState] = useState<{
    path: string;
    view: ConflictView;
  }>({ path: "", view: "parts" });
  const view = viewState.path === selectedKey ? viewState.view : "parts";
  const setView = useCallback(
    (next: ConflictView): void => {
      setViewState({ path: selectedKey, view: next });
    },
    [selectedKey],
  );

  const [activeState, setActiveState] = useState<{
    path: string;
    key: string | null;
  }>({ path: "", key: null });
  const activeHunk = activeState.path === selectedKey ? activeState.key : null;
  const setActiveHunk = useCallback(
    (key: string): void => {
      setActiveState({ path: selectedKey, key });
    },
    [selectedKey],
  );

  const detailQuery = useConflictFile(
    projectId,
    selected && needsDecision(selected) ? selected.path : null,
  );
  const detail = detailQuery.data;
  const { refetch: refetchDetail } = detailQuery;
  const reloadDetail = useCallback((): void => {
    void refetchDetail();
  }, [refetchDetail]);

  const [focusRequest, setFocusRequest] = useState<HunkFocusRequest | null>(
    null,
  );
  const focusSeq = useRef(0);
  const requestFocus = useCallback((key: string): void => {
    focusSeq.current += 1;
    setFocusRequest({ key, token: focusSeq.current });
    setActiveState((prev) => ({ ...prev, key }));
  }, []);

  const clearFocusRequest = useCallback((token: number): void => {
    setFocusRequest((prev) => (prev?.token === token ? null : prev));
  }, []);

  const [notice, setNotice] = useState<ConflictNotice | null>(null);

  const selectFile = useCallback((path: string): void => {
    setSelectedPath(path);
  }, []);

  const goNextOpenFile = useCallback((): void => {
    const next = nextOpenPath(session, draftMap, selected?.path ?? null);
    if (next) setSelectedPath(next);
  }, [draftMap, selected?.path, session]);

  // --- решения ----------------------------------------------------------------------

  const resolutionOfSelected = selected ? draftMap[selected.path] : undefined;

  const chooseHunk = useCallback(
    (key: string, choice: HunkChoice): void => {
      if (!selected) return;
      const next = setHunkChoice(draftMap[selected.path], key, choice);
      updateDraft(selected.path, (previous) =>
        setHunkChoice(previous, key, choice),
      );
      setNotice(null);
      if (isTextDetail(detail)) {
        // Сразу к следующему нерешённому месту; если их нет, фокус остаётся
        // на карточке, у которой кнопки выбора уже заменились на «Отменить».
        requestFocus(nextOpenHunkKey(detail, next, key) ?? key);
      }
    },
    [detail, draftMap, requestFocus, selected, updateDraft],
  );

  const clearHunk = useCallback(
    (key: string): void => {
      if (!selected) return;
      updateDraft(selected.path, (previous) => clearHunkChoice(previous, key));
      requestFocus(key);
    },
    [requestFocus, selected, updateDraft],
  );

  const chooseAll = useCallback(
    (choice: "mine" | "theirs"): void => {
      if (!selected || !isTextDetail(detail)) return;
      updateDraft(selected.path, chooseAllHunks(detail, choice));
      setNotice(null);
    },
    [detail, selected, updateDraft],
  );

  const chooseFile = useCallback(
    (choice: string): void => {
      if (!selected) return;
      updateDraft(selected.path, setFileChoice(choice));
      setNotice(null);
    },
    [selected, updateDraft],
  );

  const applyManual = useCallback(
    (content: string): void => {
      if (!selected) return;
      updateDraft(selected.path, setManualText(content));
      setNotice(null);
    },
    [selected, updateDraft],
  );

  const revertManual = useCallback((): void => {
    if (!selected) return;
    updateDraft(selected.path, { kind: "hunks", hunks: {} });
    setView("parts");
  }, [selected, setView, updateDraft]);

  const jumpHunk = useCallback(
    (direction: 1 | -1): void => {
      if (!isTextDetail(detail)) return;
      const next = nextOpenHunkKey(
        detail,
        resolutionOfSelected,
        activeHunk,
        direction,
      );
      if (!next) return;
      setView("parts");
      requestFocus(next);
    },
    [activeHunk, detail, requestFocus, resolutionOfSelected, setView],
  );

  // --- завершение -------------------------------------------------------------------

  const status = useSyncStatus(projectId).data;
  const resolveMutation = useResolveConflicts();
  const cancelMutation = useCancelOperation();
  const [startedId, setStartedId] = useState<string | null>(null);
  const [dismissedId, setDismissedId] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const startingRef = useRef(false);

  // Операцию могли запустить до перезагрузки страницы или в другой вкладке:
  // состояние проекта о ней знает, поэтому подхватываем её, как свою.
  const reportedId = status?.operation?.id ?? null;
  let trackedId = startedId;
  if (reportedId !== null && reportedId !== startedId) {
    trackedId = reportedId;
    setStartedId(reportedId);
  }
  const operationQuery = useOperation(trackedId);
  const operation = operationQuery.data ?? null;

  const completion = ((): ConflictCompletion => {
    if (isStarting) return { kind: "running", operation: null };
    if (trackedId === null || trackedId === dismissedId) {
      return { kind: "idle" };
    }
    if (!operation) return { kind: "running", operation: null };
    switch (operation.status) {
      case "running":
        return { kind: "running", operation };
      case "failed":
        return { kind: "failed", operation };
      case "cancelled":
        return { kind: "cancelled", operation };
      default: {
        // Слияние снова остановилось на конфликтах (репозиторий ушёл вперёд):
        // это не конец, а новый круг разбора.
        const outcome = isSyncResult(operation.result)
          ? operation.result.outcome
          : null;
        return outcome === "conflicts"
          ? { kind: "idle" }
          : { kind: "done", operation };
      }
    }
  })();

  // Итог один раз: обновляем всё, что слияние могло поменять, и уходим в историю.
  const finishedRef = useRef<string | null>(null);
  const finishedResult = operation?.result;
  const finishedOutcome = isSyncResult(finishedResult)
    ? finishedResult.outcome
    : null;
  useEffect(() => {
    if (operation?.status !== "succeeded") return;
    if (operation.id === dismissedId || finishedRef.current === operation.id) {
      return;
    }
    finishedRef.current = operation.id;
    if (finishedOutcome === "conflicts") {
      void queryClient.invalidateQueries({
        queryKey: gitSyncKeys.conflicts(projectId),
      });
      return;
    }
    invalidateAfterSync(queryClient, projectId);
    void navigate(gitHistoryPath(projectId));
  }, [
    dismissedId,
    finishedOutcome,
    navigate,
    operation,
    projectId,
    queryClient,
  ]);

  const restarted =
    operation?.status === "succeeded" &&
    finishedOutcome === "conflicts" &&
    operation.id !== dismissedId;

  const refreshAfterOutdated = useCallback(async (): Promise<void> => {
    const fresh = await gitSyncApi.getConflicts(projectId);
    queryClient.setQueryData(gitSyncKeys.conflicts(projectId), fresh);
    // Подробности и дифф старого плана больше не годятся.
    await queryClient.invalidateQueries({
      queryKey: [...gitSyncKeys.conflicts(projectId), "file"],
    });
    void queryClient.invalidateQueries({
      queryKey: [...gitSyncKeys.conflicts(projectId), "diff"],
    });
    // Выборы по местам держатся за ключи: чего в новом плане нет, убираем.
    const carried = carryOverDrafts(draftMap, fresh);
    const next: DraftMap = {};
    for (const [path, resolution] of Object.entries(carried)) {
      if (resolution.kind !== "hunks") {
        next[path] = resolution;
        continue;
      }
      try {
        const fileDetail = await queryClient.fetchQuery({
          queryKey: gitSyncKeys.conflictFile(projectId, path),
          queryFn: () => gitSyncApi.getConflictFile(projectId, path),
          staleTime: 0,
        });
        next[path] = pruneResolution(resolution, fileDetail);
      } catch {
        next[path] = resolution;
      }
    }
    replaceDrafts(next);
  }, [draftMap, projectId, queryClient, replaceDrafts]);

  const startResolve = useCallback(async (): Promise<void> => {
    if (startingRef.current) return;
    startingRef.current = true;
    setIsStarting(true);
    setNotice(null);
    try {
      if (!(await flushDrafts())) {
        setNotice({ kind: "error", message: t("notice.saveFailed") });
        return;
      }
      const started = await resolveMutation.mutateAsync({
        projectId,
        params: {
          fingerprint: session.fingerprint,
          resolutions: draftMap,
          push: true,
        },
      });
      setDismissedId(null);
      setStartedId(started.operation_id);
    } catch (error) {
      const body = readGitError(error);
      switch (body?.code) {
        case "plan_outdated":
          setNotice({ kind: "outdated" });
          try {
            await refreshAfterOutdated();
          } catch {
            // не перечитали: список обновится при следующем запросе
          }
          return;
        case "unresolved_conflicts": {
          const paths = body.paths ?? [];
          setNotice({ kind: "unresolved", count: paths.length });
          const first = paths[0];
          if (first) setSelectedPath(first);
          return;
        }
        case "no_conflicts":
          // Конфликтов уже нет: слияние закоммичено (например, отправка не
          // удалась, и проект теперь «впереди»). Повторять нечего, идём в историю.
          discardDrafts();
          invalidateAfterSync(queryClient, projectId);
          void navigate(gitHistoryPath(projectId));
          return;
        case "sync_busy":
          if (body.operation_id) setStartedId(body.operation_id);
          return;
        default:
          setNotice({
            kind: "error",
            message: describeGitError(error, t("notice.failed")),
          });
      }
    } finally {
      startingRef.current = false;
      setIsStarting(false);
    }
  }, [
    discardDrafts,
    draftMap,
    flushDrafts,
    navigate,
    projectId,
    queryClient,
    refreshAfterOutdated,
    resolveMutation,
    session.fingerprint,
    t,
  ]);

  const dismissCompletion = useCallback((): void => {
    setDismissedId(trackedId);
  }, [trackedId]);

  const cancelCompletion = useCallback((): void => {
    if (!trackedId) return;
    cancelMutation.mutate(trackedId, {
      onError: (error) => {
        toast.error(describeGitError(error, t("notice.failed")));
      },
    });
  }, [cancelMutation, t, trackedId]);

  const openHistory = useCallback((): void => {
    discardDrafts();
    invalidateAfterSync(queryClient, projectId);
    void navigate(gitHistoryPath(projectId));
  }, [discardDrafts, navigate, projectId, queryClient]);

  // --- отмена слияния ----------------------------------------------------------------

  const abortMutation = useAbortConflicts();
  const abort = useCallback(async (): Promise<void> => {
    try {
      await abortMutation.mutateAsync(projectId);
      // Сеанса больше нет: писать черновики некуда. Бросаем их только теперь,
      // иначе после неудачной отмены выборы перестали бы сохраняться.
      discardDrafts();
      toast.success(t("abort.done"));
      invalidateAfterSync(queryClient, projectId);
      void navigate(gitHistoryPath(projectId));
    } catch (error) {
      toast.error(describeGitError(error, t("abort.failed")), {
        title: t("abort.failed"),
      });
    }
  }, [abortMutation, discardDrafts, navigate, projectId, queryClient, t]);

  const dismissNotice = useCallback((): void => {
    setNotice(null);
    setDismissedId(trackedId);
  }, [trackedId]);

  const activeNotice: ConflictNotice | null =
    notice ?? (restarted ? { kind: "restarted" } : null);

  return {
    session,
    progress,
    progressOf,
    drafts,
    needs,
    auto,
    selected,
    selectFile,
    goNextOpenFile,
    view,
    setView,
    detail,
    detailLoading: detailQuery.isLoading,
    detailError: detailQuery.isError,
    reloadDetail,
    focusRequest,
    clearFocusRequest,
    activeHunk,
    setActiveHunk,
    jumpHunk,
    chooseHunk,
    clearHunk,
    chooseAll,
    chooseFile,
    applyManual,
    revertManual,
    canComplete:
      progress.open === 0 && completion.kind === "idle" && !isStarting,
    complete: startResolve,
    retryCompletion: startResolve,
    dismissCompletion,
    cancelCompletion,
    openHistory,
    isCancelling: cancelMutation.isPending,
    completion,
    abort,
    isAborting: abortMutation.isPending,
    notice: activeNotice,
    dismissNotice,
  };
};
