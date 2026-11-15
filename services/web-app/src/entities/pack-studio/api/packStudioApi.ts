import { adminClient, apiClient, ApiError, parseResp } from "@shared/api";
import { env } from "@shared/config";
import {
  PackOfficialSchema,
  PackServiceAccessCheckSchema,
  PackStudioOfficialAdminSchema,
  PackCiStatusSchema,
  PackCommitResponseSchema,
  PackDiffSchema,
  PackEditorHintsSchema,
  PackFileVersionSchema,
  PackGitSchema,
  PackLintSchema,
  PackPreviewBuildSchema,
  PackPreviewOptionsSchema,
  PackPreviewStartSchema,
  PackProposeResponseSchema,
  PackServiceAccessListSchema,
  PackServiceAccessSchema,
  PackStudioAdminSchema,
  PackStudioGrantSchema,
  PackStudioSectionSchema,
  PackTreeSchema,
  PackWorkspaceListSchema,
  PackWorkspaceSchema,
  PackYamlPatchResponseSchema,
  type CreatePackServiceAccessRequest,
  type OpenPackOfficialRequest,
  type PackOfficial,
  type PackServiceAccessCheck,
  type PackStudioOfficialAdmin,
  type UpdatePackStudioOfficialRequest,
  type CreatePackStudioGrantRequest,
  type CreatePackWorkspaceRequest,
  type PackCiStatus,
  type PackCommitResponse,
  type PackDiff,
  type PackEditorHints,
  type PackFileVersion,
  type PackGit,
  type PackLint,
  type PackPreviewBuild,
  type PackPreviewOptions,
  type PackProposeRequest,
  type PackProposeResponse,
  type PackServiceAccess,
  type PackReadOnlyReason,
  type PackStudioAdmin,
  type PackStudioGrant,
  type PackStudioSection,
  type PackTree,
  type PackWorkspace,
  type PackYamlOp,
  type PackYamlPatchResponse,
  type StartPackPreviewRequest,
} from "./schemas";

// API Студии шаблонов: /api/v1/pack-studio/* (раздел и рабочие пространства) и
// /api/admin/pack-studio (включение и права). Пути файлов идут от папки паков
// пространства; каждый сегмент кодируется отдельно, слеши остаются слешами.

const quiet = { silentError: true } as const;
const enc = encodeURIComponent;
const BASE = "/pack-studio";

const ws = (id: string) => `${BASE}/workspaces/${enc(id)}`;
const filePath = (id: string, path: string) =>
  `${ws(id)}/files/${path.split("/").map(enc).join("/")}`;

/** Версия шаблона в адресе предпросмотра: имена папок, как в дереве. */
export type PackVersionRef = {
  pack: string;
  template: string;
  version: string;
};

const versionPreview = (id: string, ref: PackVersionRef) =>
  `${ws(id)}/versions/${enc(ref.pack)}/${enc(ref.template)}/${enc(ref.version)}/preview`;
const previewBuild = (id: string, buildId: string) =>
  `${ws(id)}/previews/${enc(buildId)}`;

/** Адрес PDF собранного предпросмотра (для просмотрщика PDF: он грузит файл сам). */
export const packPreviewPdfUrl = (id: string, buildId: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1${previewBuild(id, buildId)}/pdf`;

/** Файл как текст: содержимое, версия (ETag) и почему его нельзя менять. */
export type PackFile = {
  path: string;
  content: string;
  etag: string | null;
  readOnly: PackReadOnlyReason | null;
};

const READ_ONLY_HEADER = "x-pack-read-only";

const readOnlyOf = (value: unknown): PackReadOnlyReason | null =>
  value === "version_released" || value === "releases_read_only" ? value : null;

/** Файл поменяли с тех пор, как его открыли: сервер прислал текущую версию. */
export class PackStaleFileError extends Error {
  constructor(
    readonly diskContent: string | null,
    readonly diskEtag: string | null,
  ) {
    super("pack file changed");
    this.name = "PackStaleFileError";
  }
}

const rethrowStale = (error: unknown): never => {
  if (error instanceof ApiError && error.code === "stale_file") {
    const etag = error.data?.etag;
    const content = error.data?.content;
    throw new PackStaleFileError(
      typeof content === "string" ? content : null,
      typeof etag === "string" ? etag : null,
    );
  }
  throw error;
};

export const packStudioApi = {
  section: (): Promise<PackStudioSection> =>
    apiClient
      .get(`${BASE}/section`, quiet)
      .then(parseResp(PackStudioSectionSchema)),
  setSection: (enabled: boolean): Promise<PackStudioSection> =>
    apiClient
      .put(`${BASE}/section`, { enabled })
      .then(parseResp(PackStudioSectionSchema)),

  workspaces: (): Promise<PackWorkspace[]> =>
    apiClient
      .get(`${BASE}/workspaces`, quiet)
      .then(parseResp(PackWorkspaceListSchema)),
  workspace: (id: string): Promise<PackWorkspace> =>
    apiClient.get(ws(id), quiet).then(parseResp(PackWorkspaceSchema)),
  createWorkspace: (body: CreatePackWorkspaceRequest): Promise<PackWorkspace> =>
    apiClient
      .post(`${BASE}/workspaces`, body, quiet)
      .then(parseResp(PackWorkspaceSchema)),
  deleteWorkspace: async (id: string): Promise<void> => {
    await apiClient.delete(ws(id));
  },
  refreshWorkspace: (id: string): Promise<PackWorkspace> =>
    apiClient.post(`${ws(id)}/refresh`).then(parseResp(PackWorkspaceSchema)),

  // Официальные паки (срез T22): репозиторий установки, доступ бота и
  // своё пространство; открыть отвечает уже созданным или новым (клон в фоне).
  official: (): Promise<PackOfficial> =>
    apiClient
      .get(`${BASE}/official`, quiet)
      .then(parseResp(PackOfficialSchema)),
  openOfficial: (body: OpenPackOfficialRequest): Promise<PackWorkspace> =>
    apiClient
      .post(`${BASE}/official/workspace`, body, quiet)
      .then(parseResp(PackWorkspaceSchema)),

  tree: (id: string): Promise<PackTree> =>
    apiClient.get(`${ws(id)}/tree`, quiet).then(parseResp(PackTreeSchema)),

  readFile: async (id: string, path: string): Promise<PackFile> => {
    const response = await apiClient.get<string>(filePath(id, path), {
      ...quiet,
      responseType: "text",
      // .json и .yaml не разбираются: редактору нужен текст как есть.
      transformResponse: (data: unknown) => data,
    });
    const headers = response.headers as Record<string, unknown>;
    return {
      path,
      content: typeof response.data === "string" ? response.data : "",
      etag: typeof headers.etag === "string" ? headers.etag : null,
      readOnly: readOnlyOf(headers[READ_ONLY_HEADER]),
    };
  },
  /** Запись целиком. `ifMatch`: версия, на которую опирался редактор; другая на диске даёт PackStaleFileError. */
  writeFile: (
    id: string,
    path: string,
    content: string,
    ifMatch: string | null,
  ): Promise<PackFileVersion> =>
    apiClient
      .put(filePath(id, path), content, {
        ...quiet,
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          ...(ifMatch ? { "If-Match": ifMatch } : {}),
        },
      })
      .then(parseResp(PackFileVersionSchema), rethrowStale),
  /** Точечные правки YAML (формы T11 и дальше): весь набор или ничего. */
  patchYaml: (
    id: string,
    path: string,
    ops: PackYamlOp[],
    ifMatch: string | null,
  ): Promise<PackYamlPatchResponse> =>
    apiClient
      .patch(
        filePath(id, path),
        { ops },
        { ...quiet, headers: ifMatch ? { "If-Match": ifMatch } : {} },
      )
      .then(parseResp(PackYamlPatchResponseSchema), rethrowStale),
  deleteFile: async (id: string, path: string): Promise<void> => {
    await apiClient.delete(filePath(id, path));
  },

  lint: (id: string, path: string): Promise<PackLint> =>
    apiClient
      .post(`${ws(id)}/lint`, { path }, quiet)
      .then(parseResp(PackLintSchema)),
  hints: (id: string, path: string): Promise<PackEditorHints> =>
    apiClient
      .get(`${ws(id)}/hints`, { ...quiet, params: { path } })
      .then(parseResp(PackEditorHintsSchema)),

  // Git рабочего пространства (срез T6). Операции синхронные, под замком
  // пространства: вторая одновременная отвечает workspace_busy.
  git: (id: string): Promise<PackGit> =>
    apiClient.get(`${ws(id)}/git`, quiet).then(parseResp(PackGitSchema)),
  diff: (id: string): Promise<PackDiff> =>
    apiClient.get(`${ws(id)}/git/diff`, quiet).then(parseResp(PackDiffSchema)),
  /** Без имени Студия называет ветку сама; своя прежняя или серверная только при чистом дереве. */
  switchBranch: (id: string, name: string | null): Promise<PackGit> =>
    apiClient
      .post(`${ws(id)}/git/branch`, name ? { name } : {}, quiet)
      .then(parseResp(PackGitSchema)),
  /** «Сохранить версию»: без сообщения его составляет сервер (conventional commits). */
  commit: (id: string, message: string | null): Promise<PackCommitResponse> =>
    apiClient
      .post(`${ws(id)}/git/commit`, message ? { message } : {}, {
        ...quiet,
        timeout: 120_000,
      })
      .then(parseResp(PackCommitResponseSchema)),
  /** Проверки пака, push, PR или MR: секунды, иногда дольше (свежий форк). */
  propose: (
    id: string,
    body: PackProposeRequest,
  ): Promise<PackProposeResponse> =>
    apiClient
      .post(`${ws(id)}/git/propose`, body, { ...quiet, timeout: 300_000 })
      .then(parseResp(PackProposeResponseSchema)),
  checks: (id: string): Promise<PackCiStatus> =>
    apiClient
      .get(`${ws(id)}/git/checks`, quiet)
      .then(parseResp(PackCiStatusSchema)),
  mergeBase: (id: string): Promise<PackGit> =>
    apiClient
      .post(`${ws(id)}/git/merge-base`, {}, { ...quiet, timeout: 120_000 })
      .then(parseResp(PackGitSchema)),
  /** Дерево на свежую базу без ветки; правки теряются только с `discard`. */
  startOver: (id: string, discard: boolean): Promise<PackGit> =>
    apiClient
      .post(`${ws(id)}/git/start-over`, discard ? { discard } : {}, {
        ...quiet,
        timeout: 120_000,
      })
      .then(parseResp(PackGitSchema)),

  // Предпросмотр (срез T7): варианты версии, сборка, опрос, отмена, журнал.
  previewOptions: (
    id: string,
    ref: PackVersionRef,
  ): Promise<PackPreviewOptions> =>
    apiClient
      .get(versionPreview(id, ref), quiet)
      .then(parseResp(PackPreviewOptionsSchema)),
  startPreview: (
    id: string,
    ref: PackVersionRef,
    body: StartPackPreviewRequest,
  ): Promise<PackPreviewBuild[]> =>
    apiClient
      .post(versionPreview(id, ref), body, { ...quiet, timeout: 60_000 })
      .then(parseResp(PackPreviewStartSchema))
      .then((start) => start.builds),
  previewBuild: (id: string, buildId: string): Promise<PackPreviewBuild> =>
    apiClient
      .get(previewBuild(id, buildId), quiet)
      .then(parseResp(PackPreviewBuildSchema)),
  cancelPreview: (id: string, buildId: string): Promise<PackPreviewBuild> =>
    apiClient
      .delete(previewBuild(id, buildId), quiet)
      .then(parseResp(PackPreviewBuildSchema)),
  previewLog: async (id: string, buildId: string): Promise<string> => {
    const response = await apiClient.get<string>(
      `${previewBuild(id, buildId)}/log`,
      { ...quiet, responseType: "text", transformResponse: (d: unknown) => d },
    );
    return typeof response.data === "string" ? response.data : "";
  },

  admin: (): Promise<PackStudioAdmin> =>
    adminClient.get(BASE, quiet).then(parseResp(PackStudioAdminSchema)),
  setAdmin: (enabled: boolean): Promise<PackStudioAdmin> =>
    adminClient.put(BASE, { enabled }).then(parseResp(PackStudioAdminSchema)),
  addGrant: (body: CreatePackStudioGrantRequest): Promise<PackStudioGrant> =>
    adminClient
      .post(`${BASE}/grants`, body, quiet)
      .then(parseResp(PackStudioGrantSchema)),
  removeGrant: async (grantId: string): Promise<void> => {
    await adminClient.delete(`${BASE}/grants/${enc(grantId)}`);
  },
  // Служебные доступы репозиториев паков: секрет сервер не отдаёт.
  serviceAccess: (): Promise<PackServiceAccess[]> =>
    adminClient
      .get(`${BASE}/service-access`, quiet)
      .then(parseResp(PackServiceAccessListSchema)),
  addServiceAccess: (
    body: CreatePackServiceAccessRequest,
  ): Promise<PackServiceAccess> =>
    adminClient
      .post(`${BASE}/service-access`, body, quiet)
      .then(parseResp(PackServiceAccessSchema)),
  removeServiceAccess: async (accessId: string): Promise<void> => {
    await adminClient.delete(`${BASE}/service-access/${enc(accessId)}`, quiet);
  },
  /** Проверка у хостинга: чей токен, области, у бота форк (находится или создаётся). */
  checkServiceAccess: (accessId: string): Promise<PackServiceAccessCheck> =>
    adminClient
      .post(
        `${BASE}/service-access/${enc(accessId)}/check`,
        {},
        {
          ...quiet,
          timeout: 60_000,
        },
      )
      .then(parseResp(PackServiceAccessCheckSchema)),
  officialAdmin: (): Promise<PackStudioOfficialAdmin> =>
    adminClient
      .get(`${BASE}/official`, quiet)
      .then(parseResp(PackStudioOfficialAdminSchema)),
  setOfficialAdmin: (
    body: UpdatePackStudioOfficialRequest,
  ): Promise<PackStudioOfficialAdmin> =>
    adminClient
      .put(`${BASE}/official`, body, quiet)
      .then(parseResp(PackStudioOfficialAdminSchema)),
};
