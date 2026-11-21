import type {
  PackGit,
  PackProposeResponse,
  PackRelease,
  PackVersionState,
} from "@entities/pack-studio";

// Ответы сервера для тестов и галереи области: отчёт о версии, выпуск, итог отправки.

const DRAFT = "hse-cs-sse/templates/coursework/versions/2026.1.3";

/** Отчёт черновика 2026.1.3: небольшая правка, заметок ещё нет, номер подходит. */
export const versionStateOf = (
  patch: Partial<PackVersionState> = {},
): PackVersionState => ({
  version: {
    pack: "hse-cs-sse",
    template: "coursework",
    version: "2026.1.3",
    path: DRAFT,
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
