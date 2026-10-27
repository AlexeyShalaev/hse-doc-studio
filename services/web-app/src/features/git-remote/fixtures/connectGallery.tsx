import type { QueryClient } from "@tanstack/react-query";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { profileKeys } from "@entities/profile";
import { gitRemoteKeys } from "@entities/git-remote";
import { outcomeFromProbe } from "../model/probeOutcome";
import {
  cloneVerdictFromProbe,
  type CloneVerdict,
} from "../model/cloneVerdict";
import { AccessStep } from "../ui/AccessStep";
import { DisconnectDialog } from "../ui/DisconnectDialog";
import { HostKeyDialog } from "../ui/HostKeyDialog";
import { ProfileStep } from "../ui/ProfileStep";
import { ReplaceTokenDialog } from "../ui/ReplaceTokenDialog";
import {
  CheckDemo,
  FolderDemo,
  RepositoryDemo,
  VerdictDemo,
} from "./ConnectDemos";
import {
  CONTENTS,
  DEFAULT_PROFILE,
  PAT,
  PROBE_PROJECT,
  REMOTE,
  SSH_KEY,
  failedProbe,
  makeProbe,
} from "./connectFixtures";
import { noop, urlOf, type FolderSetup, type RepoSetup } from "./galleryKit";

const HOST_KEYS = [
  {
    type: "ssh-ed25519",
    fingerprint_sha256: "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU",
  },
  {
    type: "ecdsa-sha2-nistp256",
    fingerprint_sha256: "SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM",
  },
];

// --- шаг 1: адрес -------------------------------------------------------------

const repoEntry = (
  id: string,
  title: string,
  note: string,
  setup: RepoSetup,
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  render: () => <RepositoryDemo setup={setup} />,
});

const MB = 1024 * 1024;

const repoEntries = (): GalleryEntry[] => [
  repoEntry("repo_empty", "Пустое поле", "Кнопка «Далее» недоступна.", {
    url: "",
  }),
  repoEntry(
    "repo_https",
    "Адрес по https",
    "Под полем распознан сервис и репозиторий; ниже, что попадёт в репозиторий.",
    { url: "https://github.com/hse-team/paper" },
  ),
  repoEntry(
    "repo_ssh",
    "Адрес по ssh",
    "Короткая запись git@host:owner/repo.",
    {
      url: "git@github.com:hse-team/paper.git",
    },
  ),
  repoEntry(
    "repo_branch",
    "Ветка указана",
    "Необязательное поле: по умолчанию главная ветка репозитория.",
    { url: "https://gitlab.com/hse-team/paper", branch: "develop" },
  ),
  repoEntry(
    "repo_token_stripped",
    "Токен убран из адреса",
    "Вставили адрес с токеном: токен вырезан и не сохранён, об этом написано.",
    { url: "https://github.com/hse-team/paper", tokenStripped: true },
  ),
  repoEntry(
    "repo_invalid",
    "Адрес не разобран",
    "Ошибка под полем, «Далее» недоступна.",
    { url: "github.com/hse team" },
  ),
  repoEntry(
    "repo_plain_http",
    "Открытый http",
    "По умолчанию запрещён: сообщение называет причину.",
    { url: "http://git.example.org/team/paper.git" },
  ),
  repoEntry(
    "repo_local",
    "Папка на этом компьютере",
    "Допустима для личного режима: доступ не нужен, шаг доступа пропускается.",
    { url: "file:///Users/ivan/remotes/paper.git" },
  ),
  repoEntry(
    "repo_nda",
    "Проект под NDA",
    "Без отдельного подтверждения идти дальше нельзя.",
    {
      url: "https://github.com/hse-team/paper",
      ndaRequired: true,
      contents: { ...CONTENTS, nda_files: 2 },
    },
  ),
  repoEntry(
    "repo_warnings",
    "Всё, о чём предупреждаем",
    "Версии от имени Студии, файлы LFS, подписи, папка в облаке.",
    {
      url: "https://github.com/hse-team/paper",
      sharedFolder: { provider: "yandex_disk" },
      contents: {
        ...CONTENTS,
        bot_authored_commits: 14,
        lfs_pointers: 3,
        signatures: 2,
        nda_files: 2,
      },
    },
  ),
  repoEntry(
    "repo_large_files",
    "Слишком крупные файлы в истории",
    "Дальше не пускает: список файлов крупнее лимита.",
    {
      url: "https://github.com/hse-team/paper",
      contents: {
        ...CONTENTS,
        over_limit: [
          {
            path: "video/defense-rehearsal.mov",
            bytes: 187 * MB,
            limit: 95 * MB,
          },
          { path: "data/survey-raw.csv", bytes: 112 * MB, limit: 95 * MB },
        ],
      },
    },
  ),
  repoEntry(
    "repo_loading",
    "Состав проекта загружается",
    "Заготовка вместо чисел.",
    {
      url: "https://github.com/hse-team/paper",
      contentsState: "loading",
    },
  ),
  repoEntry(
    "repo_contents_error",
    "Состав проекта не получен",
    "Сообщение и кнопка «Повторить»; подключению это не мешает.",
    {
      url: "https://github.com/hse-team/paper",
      contentsState: "error",
    },
  ),
];

// --- шаг 2: доступ ------------------------------------------------------------

type AccessSetup = {
  url: string;
  fixing?: boolean;
  bound?: { id: string; label: string; kind: string } | null;
  credentials?: (typeof PAT)[];
  loading?: boolean;
  secretsOk?: boolean;
};

const accessEntry = (
  id: string,
  title: string,
  note: string,
  setup: AccessSetup,
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  render: () => (
    <AccessStep
      url={urlOf(setup.url)}
      fixing={setup.fixing ?? false}
      bound={setup.bound ?? null}
      credentials={setup.credentials ?? []}
      isLoadingCredentials={setup.loading ?? false}
      secretsOk={setup.secretsOk ?? true}
      onContinue={noop}
      onBack={noop}
      onSwitchUrl={noop}
    />
  ),
});

const OTHER_PAT = {
  ...PAT,
  id: "cred-pat-2",
  label: "GitHub, личный",
  status: "ok" as const,
  last_used_at: "2026-10-26T08:00:00Z",
};

const accessEntries = (): GalleryEntry[] => [
  accessEntry(
    "access_https_new",
    "Токен: доступов ещё нет",
    "Как выпустить токен, где его взять и поля для вставки.",
    { url: "https://github.com/hse-team/paper" },
  ),
  accessEntry(
    "access_https_saved",
    "Токен: есть сохранённые",
    "Список сохранённых доступов для этого сервера и выбор «Новый».",
    {
      url: "https://github.com/hse-team/paper",
      credentials: [{ ...PAT, status: "ok" }, OTHER_PAT],
    },
  ),
  accessEntry(
    "access_https_loading",
    "Токен: список загружается",
    "Заготовка вместо списка доступов.",
    { url: "https://github.com/hse-team/paper", loading: true },
  ),
  accessEntry(
    "access_ssh_new",
    "Ключ ssh: ещё нет",
    "Студия создаёт ключ; показывается открытая часть и куда её вставить.",
    { url: "git@github.com:hse-team/paper.git" },
  ),
  accessEntry(
    "access_ssh_saved",
    "Ключ ssh: уже создан",
    "Отпечаток и открытая часть с кнопкой «Копировать».",
    {
      url: "git@github.com:hse-team/paper.git",
      credentials: [SSH_KEY],
    },
  ),
  accessEntry(
    "access_secrets_unavailable",
    "Хранилище секретов недоступно",
    "Токен сохранить нельзя: красная заметка вместо формы.",
    { url: "https://github.com/hse-team/paper", secretsOk: false },
  ),
  accessEntry(
    "access_fix",
    "Обновление доступа",
    "Адрес не меняется; сверху доступ, с которым проект подключён сейчас.",
    {
      url: "https://github.com/hse-team/paper",
      fixing: true,
      bound: REMOTE.credential ?? null,
      credentials: [PAT, OTHER_PAT],
    },
  ),
];

// --- шаг 3: проверка ----------------------------------------------------------

const checkEntry = (
  id: string,
  title: string,
  note: string,
  probe: ReturnType<typeof makeProbe> | null,
  options: { fixing?: boolean } = {},
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  render: () => (
    <CheckDemo
      outcome={probe ? outcomeFromProbe(probe) : null}
      probe={probe}
      fixing={options.fixing ?? false}
    />
  ),
});

const failure = (
  id: string,
  title: string,
  note: string,
  code: string,
  detail = "",
  extra: Parameters<typeof failedProbe>[2] = {},
  hostKeys: Parameters<typeof failedProbe>[3] = null,
): GalleryEntry =>
  checkEntry(id, title, note, failedProbe(code, detail, extra, hostKeys));

const checkEntries = (): GalleryEntry[] => [
  checkEntry(
    "check_running",
    "Проверка идёт",
    "Четыре строки чек-листа, итога пока нет.",
    null,
  ),
  checkEntry(
    "check_ready_empty",
    "Готово: репозиторий пуст",
    "Первая выгрузка: все версии уйдут в репозиторий.",
    makeProbe({
      empty: true,
      relation: "empty",
      project: null,
      branches: [],
      default_branch: null,
    }),
  ),
  checkEntry(
    "check_ready_same",
    "Готово: там этот же проект",
    "Репозиторий уже содержит проект с тем же именем и историей.",
    makeProbe({ relation: "same_project" }),
  ),
  checkEntry(
    "check_ready_new",
    "Готово: в репозитории проект Студии",
    "Другой проект Студии: показаны его название, шаблон и число авторов.",
    makeProbe({
      relation: "studio_project",
      project: { ...PROBE_PROJECT, name: "Диплом, черновик", authors_count: 3 },
    }),
  ),
  checkEntry(
    "check_ready_schema",
    "Готово, но проект откроется на чтение",
    "Проект записан более новой Студией: предупреждение с нужной версией.",
    makeProbe({
      schema_access: "read_only",
      required_studio: "0.4.0",
    }),
  ),
  checkEntry(
    "check_ready_template",
    "Готово, но шаблона нет",
    "Шаблона нет в этой Студии: проект откроется только на чтение.",
    makeProbe({ template_available: false }),
  ),
  checkEntry(
    "check_unrelated",
    "Тот же проект, истории не связаны",
    "Предложено объединить истории; нужно подтверждение.",
    makeProbe({ relation: "same_project_unrelated_history" }),
  ),
  checkEntry(
    "check_other_project",
    "Другой проект",
    "Подключить нельзя; можно клонировать в новую папку.",
    makeProbe({
      relation: "other_project",
      project: { ...PROBE_PROJECT, name: "Чужой проект" },
    }),
  ),
  checkEntry(
    "check_not_studio",
    "Не проект Студии",
    "В репозитории обычные файлы: подключать нельзя.",
    makeProbe({ relation: "not_studio_project", project: null }),
  ),
  checkEntry(
    "check_fix_ready",
    "Обновление доступа: готово",
    "Кнопка «Сохранить доступ» вместо «Подключить».",
    makeProbe({ relation: "same_project" }),
    { fixing: true },
  ),
  failure(
    "check_auth_failed",
    "Отказ: доступ не принят",
    "Как исправить: заменить токен.",
    "auth_failed",
    "Authentication failed for 'https://github.com/hse-team/paper'",
  ),
  failure(
    "check_forbidden_write",
    "Отказ: нельзя записывать",
    "У токена нет прав на запись.",
    "forbidden_write",
  ),
  failure(
    "check_sso",
    "Отказ: нужна авторизация в организации",
    "Токен нужно разрешить в SSO организации.",
    "sso_required",
  ),
  failure(
    "check_credentials_missing",
    "Отказ: сохранённого доступа нет",
    "Доступ удалён или не читается.",
    "credentials_missing",
  ),
  failure(
    "check_not_found",
    "Отказ: репозиторий не найден или нет доступа",
    "GitHub не различает «нет» и «нельзя»: подсказка называет оба случая.",
    "not_found_or_no_access",
  ),
  failure(
    "check_branch_missing",
    "Отказ: нет такой ветки",
    "Ветки репозитория предложены кнопками.",
    "branch_missing",
    "",
    { branches: ["main", "develop", "diploma-2026"], default_branch: "main" },
  ),
  failure(
    "check_offline",
    "Отказ: сервер не отвечает",
    "Нет сети или адрес неверен: «Повторить».",
    "offline",
    "Could not resolve host: github.com",
  ),
  failure(
    "check_timeout",
    "Отказ: слишком долго",
    "Сервер не успел ответить.",
    "timeout",
  ),
  failure(
    "check_rate_limited",
    "Отказ: слишком много запросов",
    "Нужно подождать.",
    "rate_limited",
  ),
  failure(
    "check_tls",
    "Отказ: сертификат не принят",
    "Сертификат сервера не прошёл проверку.",
    "tls_error",
  ),
  failure(
    "check_host_key_unknown",
    "Отказ: ключ сервера ещё не доверен",
    "Кнопка открывает окно с отпечатками.",
    "host_key_unknown",
    "",
    {},
    HOST_KEYS,
  ),
  failure(
    "check_host_key_changed",
    "Отказ: ключ сервера изменился",
    "Самое строгое предупреждение: это может быть подмена.",
    "host_key_changed",
    "",
    {},
    HOST_KEYS,
  ),
  failure(
    "check_ssh_unavailable",
    "Отказ: на компьютере нет ssh",
    "Установить или перейти на https.",
    "ssh_unavailable",
  ),
  failure(
    "check_git_unavailable",
    "Отказ: нет git",
    "Студия не нашла git на этом компьютере.",
    "git_unavailable",
  ),
  failure(
    "check_secrets_unavailable",
    "Отказ: хранилище секретов недоступно",
    "Сохранить токен нельзя.",
    "secrets_unavailable",
  ),
  failure(
    "check_store_untrusted",
    "Отказ: хранилище версий не доверено",
    "Папку версий скопировали с другого компьютера.",
    "store_untrusted",
  ),
  failure(
    "check_remote_exists",
    "Отказ: проект уже подключён",
    "К проекту уже привязан другой репозиторий.",
    "remote_exists",
  ),
  failure(
    "check_url_invalid",
    "Отказ: адрес не принят сервером",
    "Сервер разобрал адрес строже, чем клиент.",
    "url_invalid",
  ),
  failure(
    "check_generic",
    "Отказ: другая причина",
    "Общий вид с технической строкой.",
    "git_error",
    "fatal: unable to access: SSL_ERROR_SYSCALL",
  ),
];

// --- клонирование: итоги проверки и шаг папки ---------------------------------

const verdictEntry = (
  id: string,
  title: string,
  note: string,
  verdict: CloneVerdict,
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  render: () => <VerdictDemo verdict={verdict} />,
});

const verdictEntries = (): GalleryEntry[] => [
  verdictEntry(
    "clone_verdict_full",
    "Проект откроется полностью",
    "Зелёный итог: название, шаблон, авторы.",
    cloneVerdictFromProbe(makeProbe({ relation: "studio_project" })),
  ),
  verdictEntry(
    "clone_verdict_read_only",
    "Откроется на чтение: новая Студия",
    "Причина названа, указана нужная версия.",
    cloneVerdictFromProbe(
      makeProbe({
        relation: "studio_project",
        schema_access: "read_only",
        required_studio: "0.4.0",
      }),
    ),
  ),
  verdictEntry(
    "clone_verdict_files_only",
    "Откроется только как файлы",
    "Схема проекта слишком новая: редактировать нельзя.",
    cloneVerdictFromProbe(
      makeProbe({
        relation: "studio_project",
        schema_access: "files_only",
        required_studio: "0.5.0",
      }),
    ),
  ),
  verdictEntry(
    "clone_verdict_template",
    "Откроется на чтение: нет шаблона",
    "Шаблона нет в этой Студии.",
    cloneVerdictFromProbe(
      makeProbe({ relation: "studio_project", template_available: false }),
    ),
  ),
  verdictEntry(
    "clone_verdict_empty",
    "Репозиторий пуст",
    "Клонировать нечего.",
    cloneVerdictFromProbe(
      makeProbe({ empty: true, relation: "empty", project: null }),
    ),
  ),
  verdictEntry(
    "clone_verdict_not_studio",
    "Не проект Студии",
    "В репозитории обычные файлы.",
    cloneVerdictFromProbe(
      makeProbe({ relation: "not_studio_project", project: null }),
    ),
  ),
  verdictEntry(
    "clone_verdict_auth",
    "Отказ при проверке",
    "Те же карточки отказов, что и при подключении.",
    cloneVerdictFromProbe(failedProbe("auth_failed")),
  ),
];

const folderEntry = (
  id: string,
  title: string,
  note: string,
  setup: FolderSetup,
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  render: () => <FolderDemo setup={setup} />,
});

const folderEntries = (): GalleryEntry[] => [
  folderEntry(
    "clone_folder_idle",
    "Папка: ещё не проверена",
    "Имя и папка подсказаны по названию проекта.",
    { inspection: { state: "idle" } },
  ),
  folderEntry(
    "clone_folder_checking",
    "Папка: проверяется",
    "Короткая строка с индикатором.",
    { inspection: { state: "checking" } },
  ),
  folderEntry(
    "clone_folder_new",
    "Папки ещё нет",
    "Будет создана при клонировании.",
    { inspection: { state: "ready", exists: false } },
  ),
  folderEntry("clone_folder_empty", "Папка есть и пуста", "Подходит.", {
    inspection: { state: "ready", exists: true, isDir: true },
  }),
  folderEntry(
    "clone_folder_project",
    "В папке уже проект",
    "Клонировать поверх нельзя; названо имя проекта.",
    {
      inspection: {
        state: "ready",
        exists: true,
        isDir: true,
        hasProject: true,
        projectName: "Курсовая работа",
      },
      folderErrorCode: "project_exists",
    },
  ),
  folderEntry(
    "clone_folder_not_empty",
    "Папка не пуста",
    "Отказ запуска привязан к полю папки.",
    {
      inspection: { state: "ready", exists: true, isDir: true },
      folderErrorCode: "folder_not_empty",
    },
  ),
  folderEntry(
    "clone_folder_unavailable",
    "Папку проверить нельзя",
    "Проверка недоступна: путь вводится вручную.",
    { inspection: { state: "unavailable" } },
  ),
  folderEntry(
    "clone_folder_start_error",
    "Запуск не удался",
    "Общая ошибка над кнопками.",
    {
      inspection: { state: "ready", exists: false },
      startFailed: true,
    },
  ),
  folderEntry(
    "clone_folder_starting",
    "Запуск идёт",
    "Кнопка занята, поля заблокированы.",
    { inspection: { state: "ready", exists: false }, isStarting: true },
  ),
];

// --- окна поверх страницы -----------------------------------------------------

const dialogEntries = (): GalleryEntry[] => [
  {
    id: "dialog_profile",
    title: "Окно «Представься» внутри подключения",
    note: "Имя и e-mail автора версий; пока их нет, репозиторий не подключается.",
    frame: "window",
    seed: (client: QueryClient) => {
      client.setQueryData(profileKeys.current(), DEFAULT_PROFILE);
    },
    render: () => <ProfileStep onSaved={noop} onCancel={noop} />,
  },
  {
    id: "dialog_host_key_unknown",
    title: "Ключ сервера: новый",
    note: "Отпечатки ключей и кнопка «Доверять», которая включается через 3 секунды.",
    frame: "plain",
    render: () => (
      <DialogLauncher label="Открыть окно">
        {({ isOpen, close }) => (
          <HostKeyDialog
            isOpen={isOpen}
            mode="unknown"
            host="github.com"
            port={null}
            keys={HOST_KEYS}
            onTrusted={close}
            onClose={close}
          />
        )}
      </DialogLauncher>
    ),
  },
  {
    id: "dialog_host_key_changed",
    title: "Ключ сервера: изменился",
    note: "Красное предупреждение; чтобы принять новый ключ, нужно набрать имя сервера.",
    frame: "plain",
    render: () => (
      <DialogLauncher label="Открыть окно">
        {({ isOpen, close }) => (
          <HostKeyDialog
            isOpen={isOpen}
            mode="changed"
            host="github.com"
            port={null}
            keys={HOST_KEYS.slice(0, 1)}
            knownFingerprints={[
              "SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s",
            ]}
            onTrusted={close}
            onClose={close}
          />
        )}
      </DialogLauncher>
    ),
  },
  {
    id: "dialog_disconnect",
    title: "Отключение репозитория",
    note: "Предупреждает о неотправленных версиях и о том, кто ещё пользуется доступом.",
    frame: "plain",
    render: () => (
      <DialogLauncher label="Открыть окно">
        {({ isOpen, close }) => (
          <DisconnectDialog
            isOpen={isOpen}
            projectId="11111111-1111-4111-8111-111111111111"
            remote={REMOTE}
            unsent={4}
            credential={{
              ...PAT,
              used_by: [
                {
                  project_id: "22222222-2222-4222-8222-222222222222",
                  name: "Диплом",
                },
              ],
            }}
            onClose={close}
          />
        )}
      </DialogLauncher>
    ),
  },
  {
    id: "dialog_replace_token",
    title: "Замена токена",
    note: "Токен хранится только в окне и стирается после запроса.",
    frame: "plain",
    seed: (client: QueryClient) => {
      client.setQueryData(gitRemoteKeys.credentials(), [PAT]);
    },
    render: () => (
      <DialogLauncher label="Открыть окно">
        {({ isOpen, close }) =>
          isOpen ? (
            <ReplaceTokenDialog credential={PAT} onClose={close} />
          ) : null
        }
      </DialogLauncher>
    ),
  },
];

/** Шаги окна подключения, итоги проверки, шаги клонирования и малые окна. */
export const getRemoteStaticGallery = (): GalleryGroup[] => [
  {
    id: "connect-repo",
    title: "Подключение, шаг 1: адрес",
    entries: repoEntries(),
  },
  {
    id: "connect-access",
    title: "Подключение, шаг 2: доступ",
    entries: accessEntries(),
  },
  {
    id: "connect-check",
    title: "Подключение, шаг 3: проверка и итог",
    description:
      "Каждый исход проверки адреса: готово, предупреждения, отказы.",
    entries: checkEntries(),
  },
  {
    id: "connect-dialogs",
    title: "Окна рядом с подключением",
    entries: dialogEntries(),
  },
  {
    id: "clone-verdict",
    title: "Клонирование: итог проверки адреса",
    entries: verdictEntries(),
  },
  {
    id: "clone-folder",
    title: "Клонирование: папка",
    entries: folderEntries(),
  },
];
