import type { QueryClient } from "@tanstack/react-query";
import {
  packOutcomeKeys,
  packStudioKeys,
  type PackCiStatus,
  type PackFileChange,
  type PackGit,
  type PackLint,
  type PackTree,
  type PackVersionModel,
  type PackWorkspace,
} from "@entities/pack-studio";
import { referenceImpact } from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { SpaceProvider } from "../context/SpaceContext";
import {
  GALLERY_REF,
  GALLERY_TREE,
  GALLERY_WORKSPACE,
  SpaceGalleryFrame,
} from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { versionStateOf } from "../next-step/fixtures";
import { slots } from "./slots";

// Состояния панели «Изменения» без сервера (макет 04-changes.html): git, проверки, заметки и
// «до и после» положены в кэш запросов. Экран целиком (кнопка с числом в полосе, панель справа
// или страницей на телефоне), потому что число на кнопке и панель читают одни и те же данные.

const WS = GALLERY_WORKSPACE.id;
const DRAFT = "hse-cs-sse/templates/coursework/versions/2026.1.3";
const BRANCH = "pack-studio/anna/hse-cs-sse-coursework-2026.1.3";
const SHA = "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b";

const FILES: PackFileChange[] = [
  { path: `${DRAFT}/version.yaml`, status: "modified" },
  {
    path: `${DRAFT}/files/technical_specification/doc.yaml`,
    status: "modified",
  },
  {
    path: `${DRAFT}/files/source_listing/source_listing.ru.tex`,
    status: "modified",
  },
];

const workspaceOf = (patch: Partial<PackWorkspace> = {}): PackWorkspace => ({
  ...GALLERY_WORKSPACE,
  work_branch: BRANCH,
  ...patch,
});

const gitOf = (patch: Partial<PackGit> = {}): PackGit => ({
  workspace: workspaceOf(),
  provider: "github",
  head_sha: SHA,
  branch: BRANCH,
  base_branch: "master",
  uncommitted: FILES,
  dirty: true,
  changed: FILES,
  ahead: 0,
  behind: 0,
  compare_url: null,
  ...patch,
});

const SENT: Partial<PackGit> = {
  workspace: workspaceOf({
    pr_number: 412,
    pr_url: "https://github.com/AlexeyShalaev/hse-doc-studio/pull/412",
    pushed_sha: SHA,
  }),
  uncommitted: [],
  dirty: false,
  ahead: 2,
};

const lintOf = (findings: PackLint["findings"], target = DRAFT): PackLint => ({
  scope: "version",
  target,
  released: false,
  errors: findings.filter((f) => f.severity === "error").length,
  warnings: findings.filter((f) => f.severity === "warning").length,
  findings,
});

const WARNINGS: PackLint["findings"] = [
  {
    severity: "warning",
    check: "lint",
    message: "заголовок раздела длиннее 80 знаков",
    path: `${DRAFT}/files/technical_specification/doc.yaml`,
    line: 14,
    pointer: null,
  },
  {
    severity: "warning",
    check: "lint",
    message: "в тексте остался пробел перед запятой",
    path: `${DRAFT}/files/source_listing/source_listing.ru.tex`,
    line: 31,
    pointer: null,
  },
];

const ERRORS: PackLint["findings"] = [
  {
    severity: "error",
    check: "schema",
    message: "нет поля «name_shrt»",
    path: `${DRAFT}/files/technical_specification/doc.yaml`,
    line: 6,
    pointer: "/name_shrt",
  },
  {
    severity: "error",
    check: "lint",
    message: "version.yaml: `changes.en` — непустой список заметок о версии",
    path: `${DRAFT}/version.yaml`,
    line: null,
    pointer: null,
  },
];

const modelOf = (
  notes: { ru: string[]; en: string[] } | null,
): PackVersionModel => ({
  workspace_id: WS,
  pack: GALLERY_REF.pack,
  template: GALLERY_REF.template,
  version: GALLERY_REF.version,
  read_only: null,
  manifest: {
    path: `${DRAFT}/version.yaml`,
    etag: "e1",
    data: notes ? { changes: notes } : {},
  },
  documents: [
    {
      id: "technical_specification",
      manifest: null,
      data: { name: { ru: "Техническое задание", en: "Statement of Work" } },
      files: [],
      references: [],
    },
    {
      id: "source_listing",
      manifest: null,
      data: { name: { ru: "Текст программы", en: "Source listing" } },
      files: [],
      references: [],
    },
  ],
  usage: [],
  checks: [],
  problems: [],
  changed: [],
});

const NOTES = {
  ru: [
    "Условия выдачи технического задания: теперь только для проектной работы.",
  ],
  en: ["Statement of Work is now issued for project-type work only."],
};

const ciOf = (patch: Partial<PackCiStatus> = {}): PackCiStatus => ({
  state: "pending",
  sha: SHA,
  checks: [
    { name: "lint", state: "success", url: null, summary: null },
    { name: "schema", state: "success", url: null, summary: null },
    { name: "outcome", state: "success", url: null, summary: null },
    { name: "build-a", state: "running", url: null, summary: null },
    { name: "build-b", state: "queued", url: null, summary: null },
  ],
  available: true,
  reason: null,
  web_url: "https://github.com/AlexeyShalaev/hse-doc-studio/pull/412/checks",
  pr_state: "open",
  ...patch,
});

type Spec = {
  git?: PackGit;
  /** git читается (скелет) или не прочитался. */
  gitState?: "loading" | "failed";
  lint?: PackLint[];
  notes?: { ru: string[]; en: string[] } | null;
  ci?: PackCiStatus;
  workspace?: PackWorkspace;
  tree?: PackTree;
};

const never = () => new Promise<never>(() => undefined);

const seedOf =
  (spec: Spec) =>
  (client: QueryClient): void => {
    client.setQueryData(packStudioKeys.tree(WS), spec.tree ?? GALLERY_TREE);
    if (spec.gitState === "loading") {
      void client.prefetchQuery({
        queryKey: packStudioKeys.git(WS),
        queryFn: never,
      });
      return;
    }
    if (spec.gitState === "failed") {
      client
        .getQueryCache()
        .build(client, { queryKey: packStudioKeys.git(WS) })
        .setState({
          status: "error",
          fetchStatus: "idle",
          data: undefined,
          error: new ApiError("Сервер не ответил", "internal_error", 500),
          errorUpdateCount: 1,
          errorUpdatedAt: Date.now(),
        });
      return;
    }
    if (!spec.git) return;
    client.setQueryData(packStudioKeys.git(WS), spec.git);
    for (const report of spec.lint ?? []) {
      client.setQueryData(
        packStudioKeys.lint(WS, report.target ?? "", "0"),
        report,
      );
    }
    client.setQueryData(
      packStudioKeys.model(WS, GALLERY_REF),
      modelOf(spec.notes ?? null),
    );
    // Раздел отправки (S4) читает отчёт версии: класс, номера, записанные заметки.
    client.setQueryData(
      packStudioKeys.versionState(WS, GALLERY_REF, "0"),
      versionStateOf({ changes: spec.notes ?? { ru: [], en: [] } }),
    );
    if (spec.ci && spec.git.workspace.pushed_sha) {
      client.setQueryData(
        packStudioKeys.checks(WS, spec.git.workspace.pushed_sha),
        spec.ci,
      );
    }
    client.setQueryData(
      packOutcomeKeys.impact(WS, GALLERY_REF, {
        base: "base",
        include_atlas: true,
      }),
      { data: { ...referenceImpact("normal"), workspace_id: WS }, etag: null },
    );
  };

const screen = (
  id: string,
  title: string,
  note: string,
  spec: Spec,
  view: { phone?: boolean; version?: string; folder?: boolean } = {},
): GalleryEntry => ({
  id,
  title,
  note,
  frame: view.phone ? "plain" : "screen",
  width: view.phone ? 390 : 1280,
  seed: seedOf(spec),
  render: () =>
    view.folder ? (
      <div
        className="ui-console"
        style={{ display: "flex", flexDirection: "column", height: "34rem" }}
      >
        <SpaceProvider
          workspace={{
            ...GALLERY_WORKSPACE,
            kind: "folder",
            folder: "/Users/anna/hse-doc-studio/packs",
          }}
          tree={GALLERY_TREE}
          versionRef={GALLERY_REF}
          tab="result"
          location={{
            pathname: "/pack-studio",
            search: "changes=1",
            navigate: () => undefined,
          }}
        >
          <SpaceScreen slots={slots} phone={false} />
        </SpaceProvider>
      </div>
    ) : (
      <SpaceGalleryFrame
        search="changes=1"
        height="40rem"
        {...(view.version ? { version: view.version } : {})}
      >
        <SpaceScreen slots={slots} phone={view.phone ?? false} />
      </SpaceGalleryFrame>
    ),
});

export const galleryEntries: GalleryEntry[] = [
  screen(
    "sp_ch_ready",
    "Изменения: готово к отправке",
    "Три файла изменено, ошибок нет, два замечания не мешают; «Что изменится у студентов» считается по «до и после».",
    {
      git: gitOf({ ahead: 1 }),
      lint: [lintOf(WARNINGS)],
      notes: NOTES,
    },
  ),
  screen(
    "sp_ch_errors",
    "Изменения: есть ошибки и нужны заметки",
    "Ошибка проверки блокирует отправку и ведёт к файлу; отсутствие заметок это ожидаемый шаг, не ошибка.",
    {
      git: gitOf(),
      lint: [lintOf([...ERRORS, ...WARNINGS])],
      notes: { ru: [], en: [] },
    },
  ),
  screen(
    "sp_ch_behind",
    "Изменения: основная ветка ушла вперёд",
    "Плашка «В основной ветке есть новое» с кнопкой «Забрать новое».",
    {
      git: gitOf({ behind: 3, ahead: 1, uncommitted: [], dirty: false }),
      lint: [lintOf([])],
      notes: NOTES,
    },
  ),
  screen(
    "sp_ch_sent",
    "Изменения: запрос открыт, проверки идут",
    "Запрос #412, «Идут: 3 из 5 завершились», ссылка на запрос, можно продолжать править.",
    { git: gitOf(SENT), ci: ciOf(), lint: [lintOf([])], notes: NOTES },
  ),
  screen(
    "sp_ch_sent_edits",
    "Изменения: запрос открыт, проверки не прошли, есть новые правки",
    "Новые правки попадут в тот же запрос; проверки хостинга красные.",
    {
      git: gitOf({
        ...SENT,
        dirty: true,
        uncommitted: FILES.slice(0, 1),
      }),
      ci: ciOf({ state: "failure" }),
      lint: [lintOf(WARNINGS)],
      notes: NOTES,
    },
  ),
  screen(
    "sp_ch_merged",
    "Изменения: запрос принят",
    "«Запрос #412 принят» и кнопка «Начать новую правку».",
    {
      git: gitOf({ ...SENT, ahead: 0 }),
      ci: ciOf({ state: "success", pr_state: "merged" }),
    },
  ),
  screen(
    "sp_ch_closed",
    "Изменения: запрос закрыт без слияния",
    "Предложение сбросить свои изменения.",
    {
      git: gitOf({ ...SENT }),
      ci: ciOf({ state: "none", pr_state: "closed", checks: [] }),
    },
  ),
  screen(
    "sp_ch_empty",
    "Изменения: пока нет",
    "Объяснение, как появятся изменения, и ничего лишнего.",
    {
      git: gitOf({ changed: [], uncommitted: [], dirty: false, branch: null }),
    },
  ),
  screen(
    "sp_ch_empty_released",
    "Изменения: выпущенная версия",
    "Версия выпущена и не меняется: подсказка про «Править копию».",
    {
      git: gitOf({ changed: [], uncommitted: [], dirty: false }),
    },
    { version: "2026.1.2" },
  ),
  screen(
    "sp_ch_elsewhere",
    "Изменения: правки в другой версии",
    "Открыта выпущенная версия, а правки лежат в черновике: панель показывает их и называет версию.",
    {
      git: gitOf(),
      lint: [lintOf([])],
      notes: NOTES,
    },
    { version: "2026.1.2" },
  ),
  screen(
    "sp_ch_folder",
    "Изменения: папка на диске",
    "Правки уже записаны в папку, отправки нет; предложение подключить репозиторий.",
    {},
    { folder: true },
  ),
  screen("sp_ch_loading", "Изменения: читаем", "git ещё отвечает.", {
    gitState: "loading",
  }),
  screen(
    "sp_ch_failed",
    "Изменения: не удалось прочитать",
    "Причина и «Повторить».",
    { gitState: "failed" },
  ),
  screen(
    "sp_ch_phone",
    "Изменения: телефон",
    "Панель страницей, внизу вкладки; число на кнопке в полосе.",
    { git: gitOf({ ahead: 1 }), lint: [lintOf(WARNINGS)], notes: NOTES },
    { phone: true },
  ),
  screen(
    "sp_ch_phone_sent",
    "Изменения: телефон, запрос открыт",
    "Те же сущности и тот же путь на телефоне.",
    { git: gitOf(SENT), ci: ciOf(), lint: [lintOf([])], notes: NOTES },
    { phone: true },
  ),
];
