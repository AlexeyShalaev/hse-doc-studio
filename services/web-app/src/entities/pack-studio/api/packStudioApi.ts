import { adminClient, apiClient, ApiError, parseResp } from "@shared/api";
import {
  PackEditorHintsSchema,
  PackFileVersionSchema,
  PackLintSchema,
  PackStudioAdminSchema,
  PackStudioGrantSchema,
  PackStudioSectionSchema,
  PackTreeSchema,
  PackWorkspaceListSchema,
  PackWorkspaceSchema,
  PackYamlPatchResponseSchema,
  type CreatePackStudioGrantRequest,
  type CreatePackWorkspaceRequest,
  type PackEditorHints,
  type PackFileVersion,
  type PackLint,
  type PackReadOnlyReason,
  type PackStudioAdmin,
  type PackStudioGrant,
  type PackStudioSection,
  type PackTree,
  type PackWorkspace,
  type PackYamlOp,
  type PackYamlPatchResponse,
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
};
