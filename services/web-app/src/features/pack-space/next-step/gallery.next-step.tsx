import type { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import {
  packOutcomeKeys,
  packStudioKeys,
  type PackGit,
  type PackLint,
  type PackVersionState,
  type PackWorkspace,
} from "@entities/pack-studio";
import { referenceImpact } from "@entities/pack-studio/reference";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { SpaceProvider } from "../context/SpaceContext";
import {
  GALLERY_REF,
  GALLERY_TREE,
  GALLERY_WORKSPACE,
  SpaceGalleryFrame,
} from "../galleryKit";
import { mergeSpaceSlots } from "../shell/spaceSlots";
import { SpaceScreen } from "../shell/SpaceScreen";
import { slots as changesSlots } from "../changes/slots";
import { ForkChoice } from "./ForkChoice";
import { Progress } from "./Progress";
import { LicenseConsent } from "./LicenseConsent";
import { ReleaseOption } from "./ReleaseOption";
import {
  SENT,
  V,
  ciOf,
  gitOf,
  lintOf,
  modelOf,
  versionStateOf,
} from "./fixtures";
import { slots as nextStepSlots } from "./slots";
import type { SubmitController } from "./useSubmit";

// Состояния главной кнопки и раздела отправки без сервера (макет 04-changes.html): статус
// изменений читается из кэша запросов, поэтому кнопка и панель рисуются теми же компонентами, что
// в приложении. Ход отправки (обрыв, форк, лицензия) нельзя посеять в кэш, он живёт в состоянии
// компонента: его записи рисуют части раздела от готового контроллера.

const WS = GALLERY_WORKSPACE.id;
const SLOTS = mergeSpaceSlots([
  ["changes", changesSlots],
  ["next-step", nextStepSlots],
]);

const NOTES = {
  ru: [
    "Условия выдачи технического задания: теперь только для проектной работы.",
  ],
  en: ["Statement of Work is now issued for project-type work only."],
};

const ERRORS: PackLint["findings"] = [
  {
    severity: "error",
    check: "schema",
    message: "нет поля «name_shrt»",
    path: `${V}/files/technical_specification/doc.yaml`,
    line: 6,
    pointer: "/name_shrt",
  },
  {
    severity: "error",
    check: "schema",
    message: "в документе не указан вид работы",
    path: `${V}/files/source_listing/doc.yaml`,
    line: 2,
    pointer: null,
  },
];

type Spec = {
  git?: PackGit;
  lint?: PackLint[];
  state?: PackVersionState;
  /** Заметки записаны в версии. */
  notes?: boolean;
  ci?: ReturnType<typeof ciOf>;
  official?: boolean;
};

const seedOf =
  (spec: Spec) =>
  (client: QueryClient): void => {
    client.setQueryData(packStudioKeys.tree(WS), GALLERY_TREE);
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
      modelOf(spec.notes ?? false),
    );
    client.setQueryData(
      packStudioKeys.versionState(WS, GALLERY_REF, "0"),
      spec.state ??
        versionStateOf(
          spec.notes ? { changes: NOTES } : { changes: { ru: [], en: [] } },
        ),
    );
    if (spec.ci && spec.git.workspace.pushed_sha) {
      client.setQueryData(
        packStudioKeys.checks(WS, spec.git.workspace.pushed_sha),
        spec.ci,
      );
    }
    if (spec.official) {
      client.setQueryData(packStudioKeys.official(), {
        enabled: true,
        repo: {
          url: "https://github.com/AlexeyShalaev/hse-doc-studio.git",
          packs_path: "packs",
          base_branch: "master",
          license: "Apache-2.0",
          license_url: "https://www.apache.org/licenses/LICENSE-2.0",
          contributing_url:
            "https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/CONTRIBUTING.md",
        },
      });
    }
    client.setQueryData(
      packOutcomeKeys.impact(WS, GALLERY_REF, {
        base: "base",
        include_atlas: true,
      }),
      {
        data: { ...referenceImpact("impact_same"), workspace_id: WS },
        etag: null,
      },
    );
  };

type View = {
  phone?: boolean;
  version?: string;
  workspace?: PackWorkspace;
  /** Панель «Изменения» открыта. */
  panel?: boolean;
};

const screen = (
  id: string,
  title: string,
  note: string,
  spec: Spec,
  view: View = {},
): GalleryEntry => ({
  id,
  title,
  note,
  frame: view.phone ? "plain" : "screen",
  width: view.phone ? 390 : 1280,
  seed: seedOf(spec),
  render: () => {
    const search = view.panel === false ? "" : "changes=1";
    return view.workspace ? (
      <div
        className="ui-console"
        style={{ display: "flex", flexDirection: "column", height: "30rem" }}
      >
        <SpaceProvider
          workspace={view.workspace}
          tree={GALLERY_TREE}
          versionRef={{ ...GALLERY_REF, version: view.version ?? "2026.1.3" }}
          tab="result"
          location={{
            pathname: "/pack-studio",
            search,
            navigate: () => undefined,
          }}
        >
          <SpaceScreen slots={SLOTS} phone={false} />
        </SpaceProvider>
      </div>
    ) : (
      <SpaceGalleryFrame
        search={search}
        height="64rem"
        {...(view.version ? { version: view.version } : {})}
      >
        <SpaceScreen slots={SLOTS} phone={view.phone ?? false} />
      </SpaceGalleryFrame>
    );
  },
});

/** Контроллер раздела на готовых значениях: для частей, которые зависят от хода отправки. */
const controller = (
  patch: Partial<SubmitController> = {},
): SubmitController => ({
  available: true,
  update: false,
  version: GALLERY_REF,
  state: versionStateOf({ changes: NOTES }),
  stateLoading: false,
  notes: {
    draft: { ru: "", en: "", breakingRu: "", breakingEn: "", note: "" },
    set: () => undefined,
    suggest: () => undefined,
    canSuggest: true,
    breaking: false,
    classNote: false,
    problem: null,
    pending: false,
    saving: false,
    saved: true,
    error: null,
    flush: () => Promise.resolve(),
  },
  release: true,
  setRelease: () => undefined,
  releasable: true,
  setDefault: true,
  setSetDefault: () => undefined,
  releaseClass: "patch",
  title: "",
  setTitle: () => undefined,
  description: "",
  setDescription: () => undefined,
  consent: null,
  accepted: false,
  setAccepted: () => undefined,
  impactPending: false,
  needsAck: false,
  ack: false,
  setAck: () => undefined,
  fork: null,
  forkMode: "url",
  setForkMode: () => undefined,
  forkUrl: "",
  setForkUrl: () => undefined,
  running: false,
  plan: ["notes", "release", "send"],
  done: [],
  current: null,
  failure: null,
  outcome: null,
  blocker: null,
  run: () => undefined,
  moveTo: () => undefined,
  moving: false,
  moveError: null,
  focusNotes: () => undefined,
  ...patch,
});

const part = (
  id: string,
  title: string,
  note: string,
  view: (c: SubmitController) => React.ReactNode,
  patch: Partial<SubmitController>,
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "plain",
  width: 420,
  render: () => (
    <div className="ui-console sp-ch" style={{ padding: "1rem" }}>
      <div className="sp-ch-section sp-sb">{view(controller(patch))}</div>
    </div>
  ),
});

const none = (): void => undefined;

export const galleryEntries: GalleryEntry[] = [
  screen(
    "sp_ns_copy",
    "Главная кнопка: «Править копию»",
    "Версия выпущена, своих изменений нет: одна кнопка создаёт копию без окна выбора класса.",
    { git: gitOf({ changed: [], uncommitted: [], dirty: false }) },
    { version: "2026.1.2", panel: false },
  ),
  screen(
    "sp_ns_to_draft",
    "Главная кнопка: «К моему черновику»",
    "Открыта выпущенная версия, а правки лежат в черновике.",
    { git: gitOf(), notes: true, lint: [lintOf()] },
    { version: "2026.1.2", panel: false },
  ),
  screen(
    "sp_ns_errors",
    "Главная кнопка: «Исправить ошибки · 2»",
    "Ошибки проверки: кнопка ведёт в «Проверку»; в панели отправка выключена и называет число ошибок.",
    { git: gitOf(), lint: [lintOf(ERRORS)], notes: true },
  ),
  screen(
    "sp_ns_describe",
    "Главная кнопка: «Описать изменения»",
    "Заметок к версии ещё нет: кнопка открывает панель на полях заметок; «Подсказать по изменениям» заполняет черновик.",
    { git: gitOf(), lint: [lintOf()], notes: false },
  ),
  screen(
    "sp_ns_ready",
    "Отправка: всё готово",
    "Заметки написаны, галочка «Выпустить версию 2026.1.3» стоит; одна кнопка подтверждения в подвале.",
    { git: gitOf(), lint: [lintOf()], notes: true },
  ),
  screen(
    "sp_ns_official",
    "Отправка: официальные шаблоны",
    "Согласие с лицензией перед кнопкой отправки; без него отправить нельзя.",
    {
      git: gitOf({
        workspace: {
          ...GALLERY_WORKSPACE,
          work_branch: "pack-studio/anna/x",
          official: true,
          license_accepted_at: null,
        },
      }),
      lint: [lintOf()],
      notes: true,
      official: true,
    },
  ),
  screen(
    "sp_ns_sent",
    "Главная кнопка: запрос открыт",
    "Вторичная кнопка «Запрос #412 · проверки идут»: открывает панель.",
    { git: gitOf(SENT), ci: ciOf(), lint: [lintOf()], notes: true },
  ),
  screen(
    "sp_ns_update",
    "Главная кнопка: «Обновить запрос»",
    "После отправки были новые правки: они уйдут в тот же запрос, название и описание не спрашиваются.",
    {
      git: gitOf({ ...SENT, dirty: true, head_sha: "bbb" }),
      ci: ciOf(),
      lint: [lintOf()],
      notes: true,
      state: versionStateOf({ registered: true, changes: NOTES }),
    },
  ),
  screen(
    "sp_ns_merged",
    "Главная кнопка: «Начать новую правку»",
    "Запрос принят: следующий шаг начать от свежей основной ветки.",
    {
      git: gitOf({ ...SENT, ahead: 0 }),
      ci: ciOf({ state: "success", pr_state: "merged" }),
    },
  ),
  screen(
    "sp_ns_folder",
    "Главная кнопка: папка на диске",
    "Кнопки нет: чип «Записано в папку».",
    {},
    {
      workspace: {
        ...GALLERY_WORKSPACE,
        kind: "folder",
        folder: "/Users/anna/hse-doc-studio/packs",
      },
    },
  ),
  screen(
    "sp_ns_cloning",
    "Главная кнопка: подключаем",
    "Пока пространство подключается, вместо кнопки подпись.",
    {},
    { workspace: { ...GALLERY_WORKSPACE, state: "cloning" }, panel: false },
  ),
  screen(
    "sp_ns_failed",
    "Главная кнопка: «Проверить доступ»",
    "Подключение не удалось: кнопка открывает окно доступа к репозиторию.",
    {},
    {
      workspace: {
        ...GALLERY_WORKSPACE,
        state: "failed",
        error: { code: "workspace_git_failed", detail: "Нет доступа" },
      },
      panel: false,
    },
  ),
  part(
    "sp_ns_progress",
    "Отправка: оборвалась на выпуске",
    "Заметки записаны, выпуск не прошёл; сказано, на каком месте остановились, повтор начнётся с него.",
    (c) => <Progress c={c} onAccess={none} onOpenFile={none} />,
    {
      done: ["notes"],
      failure: {
        step: "release",
        error: new ApiError("Выпуск не удался", "workspace_git_failed", 500),
      },
    },
  ),
  part(
    "sp_ns_taken",
    "Отправка: номер уже выпущен",
    "Номер занят в основной ветке: предлагается перенести правки в свободный.",
    (c) => <Progress c={c} onAccess={none} onOpenFile={none} />,
    {
      done: ["notes"],
      failure: {
        step: "release",
        error: new ApiError("занят", "version_taken", 409, {
          suggested: "2026.1.4",
        }),
      },
    },
  ),
  part(
    "sp_ns_fork",
    "Отправка: нужна своя копия репозитория",
    "Нет права писать: объяснение, что такое форк, и выбор «создать» или «указать адрес».",
    (c) => <ForkChoice c={c} serviceAccess={false} />,
    { fork: { canCreate: true, reason: null }, forkMode: "create" },
  ),
  part(
    "sp_ns_release",
    "Отправка: номер мягче, чем нужно",
    "Выпуск выключен до смены номера; размер правки словами.",
    (c) => <ReleaseOption c={c} onNumber={none} />,
    {
      release: false,
      releasable: false,
      state: versionStateOf({
        number_ok: false,
        minimum: "minor",
        changes: NOTES,
      }),
    },
  ),
  part(
    "sp_ns_license",
    "Отправка: лицензия",
    "Согласие с лицензией и ссылки на правила вклада.",
    () => (
      <LicenseConsent
        info={{
          license: "Apache-2.0",
          licenseUrl: "https://www.apache.org/licenses/LICENSE-2.0",
          contributingUrl: "https://github.com/AlexeyShalaev/hse-doc-studio",
        }}
        checked={false}
        disabled={false}
        onChange={none}
      />
    ),
    {},
  ),
  screen(
    "sp_ns_phone",
    "Главная кнопка: телефон",
    "Кнопка на всю ширину под строкой пространства.",
    { git: gitOf(), lint: [lintOf()], notes: true },
    { phone: true, panel: false },
  ),
];
