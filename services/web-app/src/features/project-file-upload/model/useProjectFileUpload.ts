import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ApiError, apiClient } from "@shared/api/client";
import type { FileTreeItemResponse } from "@shared/api/types";
import { toast } from "@shared/lib";
import { noteProjectEdit } from "@shared/lib/editActivity";
import { encodeFilePath, fetchFileTree, fileKeys } from "@entities/document";
import { isReadOnlyRole, useProject } from "@entities/project";
import { useRouteEditGuard } from "@entities/signing-route";
import { readDropped, snapshotDrop } from "../lib/droppedFiles";
import {
  isFatal,
  serverFailure,
  type FailureReason,
  type UploadOutcome,
} from "../lib/uploadOutcome";
import {
  entriesFromFileList,
  freeCopyPath,
  planUpload,
  type ClientProblem,
  type PlannedFile,
  type UploadEntry,
} from "../lib/uploadPlan";

export type UploadKind = "files" | "folder";
export type ConflictChoice = "replace" | "keep_both" | "skip";
export type UploadPhase =
  "idle" | "preparing" | "conflict" | "uploading" | "done";

export type UploadProgress = {
  /** Номер текущего файла с единицы. */
  index: number;
  total: number;
  path: string;
  /** Доля всех байтов загрузки, 0..100. */
  percent: number;
};

export type UploadState = {
  phase: UploadPhase;
  /** Файл с таким путём уже есть; `left` вместе с ним, сколько таких ещё спросить. */
  conflict: { path: string; left: number } | null;
  progress: UploadProgress | null;
  outcomes: UploadOutcome[];
};

export type FileUploadController = {
  /** Писать в проект можно: роль не только чтение и проект не заблокирован. */
  canUpload: boolean;
  state: UploadState;
  /** Открыть выбор файлов или папки; файлы лягут в `destFolder` ("" значит корень). */
  pick: (destFolder: string, kind: UploadKind) => void;
  /** Файлы и папки, брошенные с компьютера; вызывать прямо в обработчике `drop`. */
  dropFiles: (dataTransfer: DataTransfer, destFolder: string) => void;
  /** Колбэк-ссылки на скрытые поля выбора файлов и папки (их рисует FileUploadDialog). */
  bindFilesInput: (input: HTMLInputElement | null) => void;
  bindFolderInput: (input: HTMLInputElement | null) => void;
  onInputChange: (event: ChangeEvent<HTMLInputElement>) => void;
  answerConflict: (choice: ConflictChoice, applyToAll: boolean) => void;
  /** Отменить: вопрос о совпадении закрывается без загрузки, идущая загрузка останавливается. */
  cancel: () => void;
  /** Закрыть итог. */
  close: () => void;
};

type ConflictAnswer = { choice: ConflictChoice; applyToAll: boolean } | null;

type QueuedFile = { file: File; path: string; replaced: boolean };

// Отдельной функцией: после `await` флаг мог смениться, а сужение типов этого не видит.
const isAborted = (controller: AbortController): boolean =>
  controller.signal.aborted;

const IDLE: UploadState = {
  phase: "idle",
  conflict: null,
  progress: null,
  outcomes: [],
};

const PROBLEM_BYTES: Partial<Record<ClientProblem, "max" | "free">> = {
  too_large: "max",
  quota: "free",
};

/** Папки, известные дереву: явные записи и всё, что лежит на пути к файлам. */
const knownPaths = (
  items: readonly FileTreeItemResponse[],
): { files: Set<string>; dirs: Set<string> } => {
  const files = new Set<string>();
  const dirs = new Set<string>();
  for (const item of items) {
    if (item.is_dir) dirs.add(item.path);
    else files.add(item.path);
    const segments = item.path.split("/");
    for (let i = 1; i < segments.length; i += 1) {
      dirs.add(segments.slice(0, i).join("/"));
    }
  }
  return { files, dirs };
};

/**
 * Загрузка своих файлов в проект из браузера: выбор файлов или папки, перетаскивание,
 * вопрос о совпадающих именах, ход отправки и итог. Каждый файл уходит тем же
 * `PUT /files/{path}`, что и сохранение, поэтому права, блокировки и пределы проверяет сервер;
 * то, что точно не пройдёт (размер, служебные имена, место), отсеивается ещё до отправки.
 */
export const useProjectFileUpload = (
  projectId: string,
): FileUploadController => {
  const { t } = useTranslation("fileUpload");
  const queryClient = useQueryClient();
  const { data: project } = useProject(projectId);
  const routeGuard = useRouteEditGuard(projectId);
  const [state, setState] = useState<UploadState>(IDLE);
  const filesInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const destRef = useRef("");
  const busyRef = useRef(false);
  const conflictRef = useRef<((answer: ConflictAnswer) => void) | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const canUpload =
    !isReadOnlyRole(project?.my_role) && project?.access?.mode !== "read_only";

  const askConflict = useCallback(
    (path: string, left: number): Promise<ConflictAnswer> =>
      new Promise((resolve) => {
        conflictRef.current = resolve;
        setState((prev) => ({
          ...prev,
          phase: "conflict",
          conflict: { path, left },
        }));
      }),
    [],
  );

  const resolveConflicts = useCallback(
    async (
      plan: readonly PlannedFile[],
      existingFiles: ReadonlySet<string>,
      outcomes: UploadOutcome[],
    ): Promise<QueuedFile[] | null> => {
      const taken = new Set([...existingFiles, ...plan.map((p) => p.path)]);
      const queue: QueuedFile[] = [];
      let left = plan.filter((p) => p.exists).length;
      let applied: ConflictChoice | null = null;
      for (const item of plan) {
        if (item.problem !== null) {
          const bytesKind = PROBLEM_BYTES[item.problem];
          const bytes =
            bytesKind === "max"
              ? (project?.file_max_bytes ?? undefined)
              : bytesKind === "free" && project?.storage
                ? Math.max(
                    0,
                    project.storage.limit_bytes - project.storage.used_bytes,
                  )
                : undefined;
          const reason: FailureReason =
            bytes === undefined
              ? { code: item.problem }
              : { code: item.problem, bytes };
          outcomes.push({ path: item.path, status: "failed", reason });
          continue;
        }
        if (!item.exists) {
          queue.push({ file: item.file, path: item.path, replaced: false });
          continue;
        }
        let choice = applied;
        if (choice === null) {
          const answer = await askConflict(item.path, left);
          if (answer === null) return null;
          choice = answer.choice;
          if (answer.applyToAll) applied = answer.choice;
        }
        left -= 1;
        if (choice === "skip") {
          outcomes.push({ path: item.path, status: "skipped" });
        } else if (choice === "replace") {
          queue.push({ file: item.file, path: item.path, replaced: true });
        } else {
          const copy = freeCopyPath(item.path, taken);
          taken.add(copy);
          queue.push({ file: item.file, path: copy, replaced: false });
        }
      }
      return queue;
    },
    [askConflict, project],
  );

  const send = useCallback(
    async (queue: readonly QueuedFile[], outcomes: UploadOutcome[]) => {
      const abort = new AbortController();
      abortRef.current = abort;
      const totalBytes = Math.max(
        queue.reduce((sum, item) => sum + item.file.size, 0),
        1,
      );
      let doneBytes = 0;
      let stop: FailureReason | null = null;
      for (const [index, item] of queue.entries()) {
        if (abort.signal.aborted || stop !== null) {
          outcomes.push({
            path: item.path,
            status: "failed",
            reason: stop ?? { code: "canceled" },
          });
          continue;
        }
        const progressAt = (loaded: number): void => {
          setState((prev) => ({
            ...prev,
            phase: "uploading",
            conflict: null,
            progress: {
              index: index + 1,
              total: queue.length,
              path: item.path,
              percent: ((doneBytes + loaded) / totalBytes) * 100,
            },
          }));
        };
        progressAt(0);
        try {
          await apiClient.put(
            `/projects/${projectId}/files/${encodeFilePath(item.path)}`,
            item.file,
            {
              headers: {
                "Content-Type": item.file.type || "application/octet-stream",
              },
              // Отказ показывает итог загрузки, общий тост не нужен.
              silentError: true,
              // Большой файл на медленной связи грузится дольше общего таймаута клиента.
              timeout: 0,
              signal: abort.signal,
              onUploadProgress: (event) => {
                progressAt(Math.min(event.loaded, item.file.size));
              },
            },
          );
          outcomes.push({
            path: item.path,
            status: "uploaded",
            replaced: item.replaced,
          });
        } catch (error) {
          if (isAborted(abort)) {
            outcomes.push({
              path: item.path,
              status: "failed",
              reason: { code: "canceled" },
            });
          } else {
            const reason = serverFailure(error);
            outcomes.push({ path: item.path, status: "failed", reason });
            const serverCode =
              error instanceof ApiError ? error.code : undefined;
            if (isFatal(reason, serverCode)) stop = { code: "stopped" };
          }
        }
        doneBytes += item.file.size;
      }
      abortRef.current = null;
    },
    [projectId],
  );

  const refresh = useCallback(
    (outcomes: readonly UploadOutcome[]): void => {
      const uploaded = outcomes.filter((o) => o.status === "uploaded");
      if (uploaded.length === 0) return;
      noteProjectEdit(projectId);
      void queryClient.invalidateQueries({
        queryKey: fileKeys.tree(projectId),
      });
      for (const { path } of uploaded) {
        void queryClient.invalidateQueries({
          queryKey: fileKeys.content(projectId, path),
        });
      }
    },
    [projectId, queryClient],
  );

  const run = useCallback(
    async (entries: readonly UploadEntry[], destFolder: string) => {
      if (busyRef.current) {
        toast.info(t("busy"));
        return;
      }
      if (entries.length === 0) return;
      busyRef.current = true;
      setState({ ...IDLE, phase: "preparing" });
      try {
        let tree: FileTreeItemResponse[];
        try {
          tree = await queryClient.fetchQuery({
            queryKey: fileKeys.tree(projectId),
            queryFn: () => fetchFileTree(projectId),
            staleTime: 0,
          });
        } catch {
          tree =
            queryClient.getQueryData<FileTreeItemResponse[]>(
              fileKeys.tree(projectId),
            ) ?? [];
        }
        const existing = knownPaths(tree);
        const storage = project?.storage;
        const plan = planUpload(entries, destFolder, existing, {
          maxFileBytes: project?.file_max_bytes ?? null,
          freeBytes:
            storage && storage.limit_bytes > 0
              ? Math.max(0, storage.limit_bytes - storage.used_bytes)
              : null,
        });
        if (plan.length === 0) {
          setState(IDLE);
          return;
        }
        const outcomes: UploadOutcome[] = [];
        const queue = await resolveConflicts(plan, existing.files, outcomes);
        if (queue === null) {
          setState(IDLE);
          return;
        }
        if (
          queue.length > 0 &&
          !(await routeGuard.confirm({ paths: queue.map((q) => q.path) }))
        ) {
          setState(IDLE);
          return;
        }
        await send(queue, outcomes);
        refresh(outcomes);
        const failed = outcomes.filter((o) => o.status === "failed").length;
        const uploaded = outcomes.filter((o) => o.status === "uploaded").length;
        if (failed === 0) {
          // Всё прошло: итог в тосте, окно не держим.
          if (uploaded > 0) toast.success(t("doneToast", { count: uploaded }));
          setState(IDLE);
        } else {
          setState({
            phase: "done",
            conflict: null,
            progress: null,
            outcomes,
          });
        }
      } finally {
        busyRef.current = false;
      }
    },
    [
      project,
      projectId,
      queryClient,
      refresh,
      resolveConflicts,
      routeGuard,
      send,
      t,
    ],
  );

  const bindFilesInput = useCallback((input: HTMLInputElement | null) => {
    filesInputRef.current = input;
  }, []);

  const bindFolderInput = useCallback((input: HTMLInputElement | null) => {
    // Выбор папки целиком: атрибут нестандартный, React его не знает, поэтому ставится в DOM.
    if (input) input.webkitdirectory = true;
    folderInputRef.current = input;
  }, []);

  const pick = useCallback((destFolder: string, kind: UploadKind): void => {
    destRef.current = destFolder;
    const input =
      kind === "folder" ? folderInputRef.current : filesInputRef.current;
    input?.click();
  }, []);

  const onInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>): void => {
      const entries = entriesFromFileList(event.target.files ?? []);
      // Тот же файл можно выбрать снова: без сброса браузер не пришлёт change.
      event.target.value = "";
      void run(entries, destRef.current);
    },
    [run],
  );

  const dropFiles = useCallback(
    (dataTransfer: DataTransfer, destFolder: string): void => {
      const sources = snapshotDrop(dataTransfer);
      if (sources.length === 0) return;
      readDropped(sources)
        .then((entries) => run(entries, destFolder))
        .catch(() => {
          toast.error(t("readFailed"));
        });
    },
    [run, t],
  );

  const answerConflict = useCallback(
    (choice: ConflictChoice, applyToAll: boolean): void => {
      const resolve = conflictRef.current;
      conflictRef.current = null;
      resolve?.({ choice, applyToAll });
    },
    [],
  );

  const cancel = useCallback((): void => {
    const resolve = conflictRef.current;
    if (resolve) {
      conflictRef.current = null;
      resolve(null);
      return;
    }
    abortRef.current?.abort();
  }, []);

  const close = useCallback((): void => {
    setState(IDLE);
  }, []);

  return useMemo(
    () => ({
      canUpload,
      state,
      pick,
      dropFiles,
      bindFilesInput,
      bindFolderInput,
      onInputChange,
      answerConflict,
      cancel,
      close,
    }),
    [
      canUpload,
      state,
      pick,
      dropFiles,
      bindFilesInput,
      bindFolderInput,
      onInputChange,
      answerConflict,
      cancel,
      close,
    ],
  );
};
