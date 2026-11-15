import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { sessionKeys } from "@entities/session";
import { packStudioApi, type PackVersionRef } from "./packStudioApi";
import type {
  CreatePackServiceAccessRequest,
  CreatePackStudioGrantRequest,
  CreatePackVersionRequest,
  CreatePackWorkspaceRequest,
  OpenPackOfficialRequest,
  PackCiStatus,
  PackGit,
  PackPreviewBuild,
  PackProposeRequest,
  PackReleaseRequest,
  PackVersionNotesRequest,
  PackSignaturesPatchRequest,
  PackWorkspace,
  StartPackPreviewRequest,
} from "./schemas";

export const packStudioKeys = {
  all: ["pack-studio"] as const,
  section: () => [...packStudioKeys.all, "section"] as const,
  workspaces: () => [...packStudioKeys.all, "workspaces"] as const,
  workspace: (id: string) => [...packStudioKeys.workspaces(), id] as const,
  tree: (id: string) => [...packStudioKeys.workspace(id), "tree"] as const,
  file: (id: string, path: string) =>
    [...packStudioKeys.workspace(id), "file", path] as const,
  // Проверки зависят от версии файла: новая версия даёт новый запрос.
  lint: (id: string, target: string, revision: string) =>
    [...packStudioKeys.workspace(id), "lint", target, revision] as const,
  hints: (id: string, version: string) =>
    [...packStudioKeys.workspace(id), "hints", version] as const,
  git: (id: string) => [...packStudioKeys.workspace(id), "git"] as const,
  diff: (id: string) => [...packStudioKeys.workspace(id), "diff"] as const,
  // Ключ мутаций git пространства: панель видит, что операция идёт (useIsMutating).
  gitOp: (id: string) => [...packStudioKeys.workspace(id), "git-op"] as const,
  checks: (id: string, sha: string) =>
    [...packStudioKeys.workspace(id), "checks", sha] as const,
  previewOptions: (id: string, ref: PackVersionRef) =>
    [
      ...packStudioKeys.workspace(id),
      "preview",
      ref.pack,
      ref.template,
      ref.version,
    ] as const,
  versionOptions: (id: string, pack: string, template: string) =>
    [...packStudioKeys.workspace(id), "versions", pack, template] as const,
  // Состояние версии зависит от файлов: `revision` меняется с каждой сохранённой правкой.
  versionState: (id: string, ref: PackVersionRef, revision: string) =>
    [
      ...packStudioKeys.workspace(id),
      "version-state",
      ref.pack,
      ref.template,
      ref.version,
      revision,
    ] as const,
  previewBuild: (id: string, buildId: string) =>
    [...packStudioKeys.workspace(id), "build", buildId] as const,
  // Места подписей версии: все сборки версии под одним префиксом (сброс после правки файла).
  signaturesAll: (id: string) =>
    [...packStudioKeys.workspace(id), "signatures"] as const,
  signaturesOf: (id: string, ref: PackVersionRef) =>
    [
      ...packStudioKeys.signaturesAll(id),
      ref.pack,
      ref.template,
      ref.version,
    ] as const,
  signatures: (id: string, ref: PackVersionRef, buildId: string | null) =>
    [...packStudioKeys.signaturesOf(id, ref), buildId ?? ""] as const,
  previewLog: (id: string, buildId: string) =>
    [...packStudioKeys.previewBuild(id, buildId), "log"] as const,
  admin: () => [...packStudioKeys.all, "admin"] as const,
  serviceAccess: () => [...packStudioKeys.admin(), "service-access"] as const,
  official: () => [...packStudioKeys.all, "official"] as const,
  officialAdmin: () => [...packStudioKeys.admin(), "official"] as const,
};

/** Статус проверок хостинга опрашивается раз в 30 с, пока они идут (template-studio.md, 4.4). */
export const CI_POLL_MS = 30_000;
/** Сборка предпросмотра в очереди или идёт: опрос чаще, она занимает секунды. */
export const PREVIEW_POLL_MS = 1500;

/** Проверки ждут одобрения сопровождающего: это может занять часы, спрашиваем реже. */
export const CI_APPROVAL_POLL_MS = 120_000;

/** Интервал опроса статуса проверок: раз в 30 с, пока `pending`, раз в 2 минуты,
 * пока запуск ждёт одобрения; после слияния или закрытия PR не опрашивать. */
export const ciPollInterval = (
  status: PackCiStatus | undefined,
): number | false => {
  if (status?.pr_state === "merged" || status?.pr_state === "closed") {
    return false;
  }
  if (status?.state === "pending") return CI_POLL_MS;
  if (status?.state === "awaiting_approval") return CI_APPROVAL_POLL_MS;
  return false;
};

/** Интервал опроса сборки предпросмотра: пока она в очереди или идёт. */
export const previewPollInterval = (
  build: PackPreviewBuild | undefined,
): number | false =>
  build?.status === "queued" || build?.status === "running"
    ? PREVIEW_POLL_MS
    : false;

/** Пока идёт клон или выборка, карточку опрашиваем: фоновая операция без operation_id. */
export const WORKSPACE_POLL_MS = 1500;

const pollWhileBusy = (workspace: PackWorkspace | undefined): number | false =>
  workspace?.busy ? WORKSPACE_POLL_MS : false;

export const usePackStudioSection = (enabled = true) =>
  useQuery({
    queryKey: packStudioKeys.section(),
    queryFn: () => packStudioApi.section(),
    enabled,
  });

/** Переключатель «Инструменты автора шаблонов» локальной Студии; возможность в bootstrap меняется с ним. */
export const useSetPackStudioSection = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => packStudioApi.setSection(enabled),
    onSuccess: (section) => {
      client.setQueryData(packStudioKeys.section(), section);
      void client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });
    },
  });
};

export const usePackWorkspaces = () =>
  useQuery({
    queryKey: packStudioKeys.workspaces(),
    queryFn: () => packStudioApi.workspaces(),
    refetchInterval: (query) =>
      query.state.data?.some((w) => w.busy) ? WORKSPACE_POLL_MS : false,
  });

export const usePackWorkspace = (id: string) =>
  useQuery({
    queryKey: packStudioKeys.workspace(id),
    queryFn: () => packStudioApi.workspace(id),
    refetchInterval: (query) => pollWhileBusy(query.state.data),
  });

const rememberWorkspace = (client: QueryClient, workspace: PackWorkspace) => {
  client.setQueryData(packStudioKeys.workspace(workspace.id), workspace);
  void client.invalidateQueries({
    queryKey: packStudioKeys.workspaces(),
    exact: true,
  });
};

export const useCreatePackWorkspace = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePackWorkspaceRequest) =>
      packStudioApi.createWorkspace(body),
    onSuccess: (workspace) => {
      rememberWorkspace(client, workspace);
    },
  });
};

// ── официальные паки (срез T22) ─────────────────────────────────────────────

export const usePackOfficial = (enabled = true) =>
  useQuery({
    queryKey: packStudioKeys.official(),
    queryFn: () => packStudioApi.official(),
    enabled,
  });

export const useOpenPackOfficial = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: OpenPackOfficialRequest) =>
      packStudioApi.openOfficial(body),
    onSuccess: (workspace) => {
      rememberWorkspace(client, workspace);
      void client.invalidateQueries({ queryKey: packStudioKeys.official() });
    },
  });
};

export const useRefreshPackWorkspace = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => packStudioApi.refreshWorkspace(id),
    onSuccess: (workspace) => {
      rememberWorkspace(client, workspace);
      void client.invalidateQueries({
        queryKey: packStudioKeys.tree(workspace.id),
      });
    },
  });
};

export const useDeletePackWorkspace = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => packStudioApi.deleteWorkspace(id),
    onSuccess: (_, id) => {
      client.removeQueries({ queryKey: packStudioKeys.workspace(id) });
      void client.invalidateQueries({ queryKey: packStudioKeys.workspaces() });
    },
  });
};

export const usePackTree = (id: string, enabled = true) =>
  useQuery({
    queryKey: packStudioKeys.tree(id),
    queryFn: () => packStudioApi.tree(id),
    enabled,
  });

export const usePackFile = (id: string, path: string | null) =>
  useQuery({
    queryKey: packStudioKeys.file(id, path ?? ""),
    queryFn: () => packStudioApi.readFile(id, path ?? ""),
    enabled: path !== null,
    // Открытый файл не перечитывается сам: внешнюю правку покажет конфликт при записи.
    staleTime: Infinity,
    gcTime: 0,
  });

/**
 * Проверки версии или манифеста, к которому относится файл. `target` это каталог
 * версии или сам манифест (lintTargetOf): одна проверка на всю версию, сколько бы
 * её файлов ни было открыто. `revision` меняется с каждой сохранённой правкой.
 */
export const usePackLint = (
  id: string,
  target: string | null,
  revision: string,
) =>
  useQuery({
    queryKey: packStudioKeys.lint(id, target ?? "", revision),
    queryFn: () => packStudioApi.lint(id, target ?? ""),
    enabled: target !== null,
    placeholderData: (previous) => previous,
    staleTime: Infinity,
  });

/** Подсказки автодополнения версии (`version`: каталог версии файла, versionDirOf). */
export const usePackHints = (id: string, version: string | null) =>
  useQuery({
    queryKey: packStudioKeys.hints(id, version ?? ""),
    queryFn: () => packStudioApi.hints(id, version ?? ""),
    enabled: version !== null,
    staleTime: 60_000,
  });

// ── git рабочего пространства (срез T6) ─────────────────────────────────────

export const usePackGit = (id: string, enabled = true) =>
  useQuery({
    queryKey: packStudioKeys.git(id),
    queryFn: () => packStudioApi.git(id),
    enabled,
  });

/** Ответ операции git несёт и карточку пространства: обе в кэш, diff перечитается. */
const rememberGit = (client: QueryClient, git: PackGit) => {
  client.setQueryData(packStudioKeys.git(git.workspace.id), git);
  rememberWorkspace(client, git.workspace);
  void client.invalidateQueries({
    queryKey: packStudioKeys.diff(git.workspace.id),
  });
};

/**
 * Операция поменяла файлы на диске (другая ветка, слияние базы, начать заново):
 * дерево, открытые файлы и проверки читаются заново.
 */
const forgetFiles = (client: QueryClient, id: string) => {
  void client.invalidateQueries({ queryKey: packStudioKeys.tree(id) });
  client.removeQueries({ queryKey: [...packStudioKeys.workspace(id), "file"] });
  client.removeQueries({ queryKey: [...packStudioKeys.workspace(id), "lint"] });
};

export const usePackDiff = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: packStudioKeys.diff(id),
    queryFn: () => packStudioApi.diff(id),
    enabled,
    staleTime: 0,
  });

export const useSwitchPackBranch = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationKey: packStudioKeys.gitOp(id),
    mutationFn: (name: string | null) => packStudioApi.switchBranch(id, name),
    onSuccess: (git) => {
      rememberGit(client, git);
      forgetFiles(client, id);
    },
  });
};

export const useCommitPack = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationKey: packStudioKeys.gitOp(id),
    mutationFn: (message: string | null) => packStudioApi.commit(id, message),
    onSuccess: (result) => {
      rememberGit(client, result.git);
    },
  });
};

export const useProposePack = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationKey: packStudioKeys.gitOp(id),
    mutationFn: (body: PackProposeRequest) => packStudioApi.propose(id, body),
    onSuccess: (result) => {
      rememberGit(client, result.git);
      void client.invalidateQueries({
        queryKey: [...packStudioKeys.workspace(id), "checks"],
      });
    },
  });
};

export const useMergePackBase = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationKey: packStudioKeys.gitOp(id),
    mutationFn: () => packStudioApi.mergeBase(id),
    onSuccess: (git) => {
      rememberGit(client, git);
      forgetFiles(client, id);
    },
  });
};

export const useStartPackOver = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationKey: packStudioKeys.gitOp(id),
    mutationFn: (discard: boolean) => packStudioApi.startOver(id, discard),
    onSuccess: (git) => {
      rememberGit(client, git);
      forgetFiles(client, id);
    },
  });
};

// ── мастер «Новая версия» (срез T10) ───────────────────────────────────────

export const usePackVersionOptions = (
  id: string,
  pack: string,
  template: string,
  enabled = true,
) =>
  useQuery({
    queryKey: packStudioKeys.versionOptions(id, pack, template),
    queryFn: () => packStudioApi.versionOptions(id, pack, template),
    enabled,
    staleTime: 0,
  });

/** Живой класс версии: перечитывается с каждой сохранённой правкой (`revision`). */
export const usePackVersionState = (
  id: string,
  ref: PackVersionRef | null,
  revision: string,
) =>
  useQuery({
    queryKey: packStudioKeys.versionState(
      id,
      ref ?? { pack: "", template: "", version: "" },
      revision,
    ),
    queryFn: () =>
      packStudioApi.versionState(
        id,
        ref ?? { pack: "", template: "", version: "" },
      ),
    enabled: ref !== null,
    placeholderData: (previous) => previous,
    staleTime: Infinity,
  });

/** Шаг мастера поменял файлы: дерево, состояние версий, git и проверки читаются заново. */
const forgetVersionFiles = (client: QueryClient, id: string) => {
  void client.invalidateQueries({ queryKey: packStudioKeys.tree(id) });
  void client.invalidateQueries({ queryKey: packStudioKeys.git(id) });
  void client.invalidateQueries({
    queryKey: [...packStudioKeys.workspace(id), "version-state"],
  });
  void client.invalidateQueries({
    queryKey: [...packStudioKeys.workspace(id), "versions"],
  });
  client.removeQueries({ queryKey: [...packStudioKeys.workspace(id), "file"] });
  client.removeQueries({ queryKey: [...packStudioKeys.workspace(id), "lint"] });
};

export const useCreatePackVersion = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      pack: string;
      template: string;
      body: CreatePackVersionRequest;
    }) => packStudioApi.createVersion(id, args.pack, args.template, args.body),
    onSuccess: () => {
      forgetVersionFiles(client, id);
    },
  });
};

export const useSavePackVersionNotes = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      ref: PackVersionRef;
      body: PackVersionNotesRequest;
    }) => packStudioApi.saveVersionNotes(id, args.ref, args.body),
    onSuccess: () => {
      forgetVersionFiles(client, id);
    },
  });
};

export const useRenumberPackVersion = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: { ref: PackVersionRef; version: string }) =>
      packStudioApi.renumberVersion(id, args.ref, args.version),
    onSuccess: () => {
      forgetVersionFiles(client, id);
    },
  });
};

export const useMovePackVersionEdits = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: { ref: PackVersionRef; version: string | null }) =>
      packStudioApi.moveVersionEdits(id, args.ref, args.version),
    onSuccess: () => {
      forgetVersionFiles(client, id);
    },
  });
};

export const useReleasePackVersion = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: { ref: PackVersionRef; body: PackReleaseRequest }) =>
      packStudioApi.releaseVersion(id, args.ref, args.body),
    onSuccess: () => {
      forgetVersionFiles(client, id);
      // Выпуск у git делает выборку базы: карточка пространства тоже свежая.
      void client.invalidateQueries({ queryKey: packStudioKeys.workspace(id) });
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: packStudioKeys.tree(id) });
    },
  });
};

/** Статус проверок по отправленной вершине: опрос раз в 30 с, пока `pending`. */
export const usePackChecks = (id: string, sha: string | null) =>
  useQuery({
    queryKey: packStudioKeys.checks(id, sha ?? ""),
    queryFn: () => packStudioApi.checks(id),
    enabled: sha !== null,
    refetchInterval: (query) => ciPollInterval(query.state.data),
  });

// ── предпросмотр (срез T7) ──────────────────────────────────────────────────

export const usePackPreviewOptions = (id: string, ref: PackVersionRef | null) =>
  useQuery({
    queryKey: packStudioKeys.previewOptions(
      id,
      ref ?? { pack: "", template: "", version: "" },
    ),
    queryFn: () =>
      packStudioApi.previewOptions(
        id,
        ref ?? { pack: "", template: "", version: "" },
      ),
    enabled: ref !== null,
  });

export const useStartPackPreview = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      ref,
      body,
    }: {
      ref: PackVersionRef;
      body: StartPackPreviewRequest;
    }) => packStudioApi.startPreview(id, ref, body),
    onSuccess: (builds) => {
      for (const build of builds) {
        client.setQueryData(packStudioKeys.previewBuild(id, build.id), build);
      }
    },
  });
};

/** Сборка опрашивается, пока она в очереди или идёт. */
export const usePackPreviewBuild = (id: string, buildId: string | null) =>
  useQuery({
    queryKey: packStudioKeys.previewBuild(id, buildId ?? ""),
    queryFn: () => packStudioApi.previewBuild(id, buildId ?? ""),
    enabled: buildId !== null,
    refetchInterval: (query) => previewPollInterval(query.state.data),
  });

export const useCancelPackPreview = (id: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (buildId: string) => packStudioApi.cancelPreview(id, buildId),
    onSuccess: (build) => {
      client.setQueryData(packStudioKeys.previewBuild(id, build.id), build);
    },
  });
};

export const usePackPreviewLog = (id: string, buildId: string | null) =>
  useQuery({
    queryKey: packStudioKeys.previewLog(id, buildId ?? ""),
    queryFn: () => packStudioApi.previewLog(id, buildId ?? ""),
    enabled: buildId !== null,
  });

export const usePackStudioAdmin = () =>
  useQuery({
    queryKey: packStudioKeys.admin(),
    queryFn: () => packStudioApi.admin(),
  });

export const useSetPackStudioAdmin = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => packStudioApi.setAdmin(enabled),
    onSuccess: (admin) => {
      client.setQueryData(packStudioKeys.admin(), admin);
      void client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });
    },
  });
};

export const useAddPackStudioGrant = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePackStudioGrantRequest) =>
      packStudioApi.addGrant(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: packStudioKeys.admin() });
    },
  });
};

export const useRemovePackStudioGrant = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (grantId: string) => packStudioApi.removeGrant(grantId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: packStudioKeys.admin() });
    },
  });
};

export const usePackServiceAccess = () =>
  useQuery({
    queryKey: packStudioKeys.serviceAccess(),
    queryFn: () => packStudioApi.serviceAccess(),
  });

export const useAddPackServiceAccess = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePackServiceAccessRequest) =>
      packStudioApi.addServiceAccess(body),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: packStudioKeys.serviceAccess(),
      });
    },
  });
};

/** «Проверить» служебный доступ у хостинга: только чтение, кэш не меняется. */
export const useCheckPackServiceAccess = () =>
  useMutation({
    mutationFn: (accessId: string) =>
      packStudioApi.checkServiceAccess(accessId),
  });

export const usePackOfficialAdmin = () =>
  useQuery({
    queryKey: packStudioKeys.officialAdmin(),
    queryFn: () => packStudioApi.officialAdmin(),
  });

export const useRemovePackServiceAccess = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (accessId: string) =>
      packStudioApi.removeServiceAccess(accessId),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: packStudioKeys.serviceAccess(),
      });
    },
  });
};

/** Места подписей версии (срез T9): каталог слотов и рамки документа сборки `buildId`. */
export const usePackSignatures = (
  id: string,
  ref: PackVersionRef | null,
  buildId: string | null,
) =>
  useQuery({
    queryKey: packStudioKeys.signatures(
      id,
      ref ?? { pack: "", template: "", version: "" },
      buildId,
    ),
    queryFn: () =>
      packStudioApi.signatures(
        id,
        ref ?? { pack: "", template: "", version: "" },
        buildId,
      ),
    enabled: ref !== null,
  });

/**
 * Правка мест: ответ сразу ложится в кэш (тот же запрос со сборкой), а запросы мест этой версии с другими
 * сборками помечаются устаревшими. `If-Match` берётся из последнего ответа.
 */
export const usePatchPackSignatures = (
  id: string,
  ref: PackVersionRef,
  buildId: string | null,
) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      body,
      etag,
    }: {
      body: PackSignaturesPatchRequest;
      etag: string | null;
    }) => packStudioApi.patchSignatures(id, ref, body, etag),
    onSuccess: (data) => {
      const key = packStudioKeys.signatures(id, ref, buildId);
      void client.invalidateQueries({
        queryKey: packStudioKeys.signaturesOf(id, ref),
        predicate: (query) =>
          JSON.stringify(query.queryKey) !== JSON.stringify(key),
      });
      client.setQueryData(key, data);
      void client.invalidateQueries({
        queryKey: packStudioKeys.file(id, data.path),
      });
      void client.invalidateQueries({ queryKey: packStudioKeys.git(id) });
    },
  });
};
