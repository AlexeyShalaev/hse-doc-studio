import type {
  PackCiStatus,
  PackFileChange,
  PackGit,
  PackLint,
  PackProposeResponse,
  PackRelease,
  PackVersionModel,
  PackVersionState,
} from "@entities/pack-studio";
import { GALLERY_WORKSPACE } from "../galleryKit";

// Ответы сервера для тестов и галереи области: отчёт о версии, выпуск, итог отправки.

/** Отчёт черновика 2026.1.3: небольшая правка, заметок ещё нет, номер подходит. */
export const versionStateOf = (
  patch: Partial<PackVersionState> = {},
): PackVersionState => ({
  version: {
    pack: "hse-cs-sse",
    template: "coursework",
    version: "2026.1.3",
    path: V,
  },
  status: "beta",
  released: false,
  modified: false,
  registered: false,
  release_outdated: false,
  is_default: false,
  base: "2026.1.2",
  minimum: "patch",
  suggested: "patch",
  by_number: "patch",
  declared: null,
  note: null,
  number_ok: true,
  headline: { ru: "Небольшая правка", en: "Small fix" },
  reasons: [],
  numbers: { patch: "2026.1.3", minor: "2026.2.0", major: "2027.1.0" },
  changes: { ru: [], en: [] },
  breaking_changes: { ru: [], en: [] },
  draft_changes: {
    ru: ["Условия выдачи технического задания: только для проектной работы."],
    en: ["Statement of Work is now issued for project-type work only."],
  },
  draft_breaking: { ru: [], en: [] },
  move_to: null,
  error: null,
  ...patch,
});

export const releaseOf = (
  version = "2026.1.3",
  patch: Partial<PackRelease> = {},
): PackRelease => ({
  version: {
    pack: "hse-cs-sse",
    template: "coursework",
    version,
    path: `hse-cs-sse/templates/coursework/versions/${version}`,
  },
  digest: "sha256:abc",
  kind: "patch",
  previous: null,
  replaced: false,
  default_set: true,
  edited: [],
  warnings: [],
  ...patch,
});

/** Итог отправки: запрос #412 открыт. */
export const proposeOf = (
  git: PackGit,
  patch: Partial<PackProposeResponse> = {},
): PackProposeResponse => ({
  git,
  pushed_sha: "9a8b7c6",
  pushed_to: "https://github.com/AlexeyShalaev/hse-doc-studio.git",
  pull_request: {
    number: 412,
    url: "https://github.com/AlexeyShalaev/hse-doc-studio/pull/412",
    created: true,
  },
  compare_url: null,
  pr_error: null,
  checks: { errors: 0, warnings: 0, findings: [], classes: [] },
  ...patch,
});

export const V = "hse-cs-sse/templates/coursework/versions/2026.1.3";
export const BRANCH = "pack-studio/anna/hse-cs-sse-coursework-2026.1.3";

export const FILES: PackFileChange[] = [
  { path: `${V}/version.yaml`, status: "modified" },
  { path: `${V}/files/technical_specification/doc.yaml`, status: "modified" },
  {
    path: `${V}/files/source_listing/source_listing.ru.tex`,
    status: "modified",
  },
];

export const gitOf = (patch: Partial<PackGit> = {}): PackGit => ({
  workspace: { ...GALLERY_WORKSPACE, work_branch: BRANCH },
  provider: "github",
  head_sha: "aaa",
  branch: BRANCH,
  base_branch: "master",
  uncommitted: FILES,
  dirty: true,
  changed: FILES,
  ahead: 1,
  behind: 0,
  compare_url: null,
  ...patch,
});

/** Запрос #412 открыт, новых правок нет. */
export const SENT: Partial<PackGit> = {
  workspace: {
    ...GALLERY_WORKSPACE,
    work_branch: BRANCH,
    pr_number: 412,
    pr_url: "https://github.com/o/r/pull/412",
    pushed_sha: "aaa",
  },
  uncommitted: [],
  dirty: false,
};

export const lintOf = (findings: PackLint["findings"] = []): PackLint => ({
  scope: "version",
  target: V,
  released: false,
  errors: findings.filter((f) => f.severity === "error").length,
  warnings: findings.filter((f) => f.severity === "warning").length,
  findings,
});

export const modelOf = (notes: boolean): PackVersionModel => ({
  workspace_id: GALLERY_WORKSPACE.id,
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.3",
  read_only: null,
  manifest: {
    path: `${V}/version.yaml`,
    etag: "e",
    data: notes ? { changes: { ru: ["Раз"], en: ["One"] } } : {},
  },
  documents: [],
  usage: [],
  checks: [],
  problems: [],
  changed: [],
});

export const ciOf = (patch: Partial<PackCiStatus> = {}): PackCiStatus => ({
  state: "pending",
  sha: "aaa",
  checks: [
    { name: "a", state: "success", url: null, summary: null },
    { name: "b", state: "running", url: null, summary: null },
  ],
  available: true,
  reason: null,
  web_url: null,
  pr_state: "open",
  ...patch,
});
