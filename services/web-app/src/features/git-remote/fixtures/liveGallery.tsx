import type { ConnectDialogMode } from "@entities/git-sync";
import {
  GALLERY_PROJECT_ID,
  type GalleryEntry,
  type GalleryGroup,
} from "@shared/lib/stateGallery";
import { ConnectLauncher } from "./ConnectLauncher";
import { CloneWizard } from "../ui/clone/CloneWizard";
import { GitAccessSection } from "../ui/GitAccessSection";
import {
  FetchOptionsCard,
  RemoteConnectionCard,
  SharedFolderCard,
} from "../ui/RemoteSettingsCards";

const noop = (): void => undefined;

const connectEntry = (
  id: string,
  title: string,
  note: string,
  scenario: string,
  mode: ConnectDialogMode = "connect",
  url?: string,
): GalleryEntry => ({
  id,
  title,
  note,
  scenario,
  frame: "plain",
  render: () => (
    <ConnectLauncher mode={mode} {...(url === undefined ? {} : { url })} />
  ),
});

const cloneEntry = (
  id: string,
  title: string,
  note: string,
  url: string | null,
): GalleryEntry => ({
  id,
  title,
  note,
  scenario: "not_connected",
  // Мастер сам рисует отступы страницы: ещё одна рамка с полями была бы лишней.
  frame: "page",
  render: () => (
    <CloneWizard
      initialTarget={url === null ? null : { url, credentialId: null }}
      onExit={noop}
      onOpenProject={noop}
    />
  ),
});

const cardEntry = (
  id: string,
  title: string,
  note: string,
  scenario: string,
  card: "connection" | "fetch" | "shared",
): GalleryEntry => ({
  id,
  title,
  note,
  scenario,
  frame: "window",
  render: () => {
    if (card === "fetch")
      return <FetchOptionsCard projectId={GALLERY_PROJECT_ID} />;
    if (card === "shared")
      return <SharedFolderCard projectId={GALLERY_PROJECT_ID} />;
    return <RemoteConnectionCard projectId={GALLERY_PROJECT_ID} />;
  },
});

const TOKEN_HINT = "Адрес уже в поле. После «Далее» вставь любой токен.";

// Живые записи про серверы и токены: адрес подставлен, сценарий выбирается сам.
const accessLiveGroups = (): GalleryGroup[] => [
  {
    id: "live-providers",
    title: "Серверы и токены (живое)",
    description:
      "Окно подключения с готовым адресом. Токен подойдёт любой: слова в нём (narrow, broad, expired, revoked, opaque) задают исход проверки.",
    entries: [
      connectEntry(
        "live_provider_gitlab_com",
        "GitLab.com: токен по ссылке",
        `${TOKEN_HINT} Кнопка «Создать токен на GitLab» открывает страницу с подставленными правами.`,
        "provider_gitlab_com",
        "connect",
        "https://gitlab.com/hse/paper.git",
      ),
      connectEntry(
        "live_provider_gitlab_self",
        "Свой GitLab 17",
        `${TOKEN_HINT} В чипе версия сервера, ссылка ведёт на страницу токенов этого сервера.`,
        "provider_gitlab_self",
        "connect",
        "https://gitlab.hse.ru/team/paper.git",
      ),
      connectEntry(
        "live_provider_gitlab_old",
        "Старый GitLab 13: запасная ссылка",
        `${TOKEN_HINT} Основная ссылка может не открыться, рядом запасная; права токена прочитать нельзя.`,
        "provider_gitlab_old",
        "connect",
        "https://gitlab.old.hse.ru/team/paper.git",
      ),
      connectEntry(
        "live_provider_api_detect",
        "Тип сервера по его ответу",
        "По имени хоста тип не понять: сервер называет себя GitLab 16, это видно в чипе.",
        "provider_api_detect",
        "connect",
        "https://forge.hse.ru/team/paper.git",
      ),
      connectEntry(
        "live_provider_github",
        "GitHub: точный токен",
        `${TOKEN_HINT} Под кнопкой напоминание выбрать репозиторий; токен github_pat_demo проверить по правам нельзя.`,
        "provider_github",
        "connect",
        "https://github.com/hse/paper.git",
      ),
      connectEntry(
        "live_provider_gitea",
        "Gitea и Codeberg: шаги по номерам",
        `${TOKEN_HINT} Ссылка без подстановки прав и шаги по номерам.`,
        "provider_gitea",
        "connect",
        "https://codeberg.org/anna/paper.git",
      ),
    ],
  },
  {
    id: "live-tokens",
    title: "Итоги проверки токена (живое)",
    entries: [
      connectEntry(
        "live_token_narrow",
        "Токену не хватает прав",
        `${TOKEN_HINT} Проверка называет право, которое нужно добавить (write_repository).`,
        "token_narrow",
        "connect",
        "https://gitlab.com/hse/paper.git",
      ),
      connectEntry(
        "live_token_broad",
        "У токена слишком много прав",
        `${TOKEN_HINT} Предупреждение про право api, подключиться можно.`,
        "token_broad",
        "connect",
        "https://gitlab.com/hse/paper.git",
      ),
      connectEntry(
        "live_token_expired",
        "Срок токена истёк",
        `${TOKEN_HINT} Проверка говорит, когда токен истёк, и предлагает выпустить новый.`,
        "token_expired",
        "connect",
        "https://gitlab.com/hse/paper.git",
      ),
      connectEntry(
        "live_token_opaque",
        "Права проверить нельзя",
        `${TOKEN_HINT} Это не отказ: сервер не отдаёт права токена, доступ проверит само подключение.`,
        "token_opaque",
        "connect",
        "https://gitlab.com/hse/paper.git",
      ),
    ],
  },
  {
    id: "live-certificates",
    title: "Сертификат сервера (живое)",
    description:
      "Окно сертификата можно пройти до конца: добавить центр выдачи (подойдёт любой текст между BEGIN CERTIFICATE и END CERTIFICATE) или закрепить отпечаток.",
    entries: [
      connectEntry(
        "live_tls_ca",
        "Сертификат организации",
        `${TOKEN_HINT} После «Сохранить и проверить» откроется окно сертификата: добавь центр выдачи.`,
        "provider_tls_ca",
        "connect",
        "https://gitlab.hse.local/team/paper.git",
      ),
      connectEntry(
        "live_tls_selfsigned",
        "Самоподписанный сертификат",
        `${TOKEN_HINT} Окно предложит закрепить отпечаток после сверки.`,
        "provider_tls_selfsigned",
        "connect",
        "https://gitlab.lab.local/team/paper.git",
      ),
      connectEntry(
        "live_tls_pin_changed",
        "Сертификат изменился после закрепления",
        `${TOKEN_HINT} Видны оба отпечатка; чтобы закрепить новый, нужно набрать имя сервера.`,
        "provider_tls_pin_changed",
        "connect",
        "https://gitlab.rotated.local/team/paper.git",
      ),
    ],
  },
  {
    id: "live-servers",
    title: "Настройки приложения: доступ к git (живое)",
    entries: [
      {
        id: "live_access_expiry",
        title: "Доступы с разным сроком",
        note: "Скоро истекает, истёк, без срока; у каждого токена кнопка «Проверить».",
        scenario: "credentials_expiry",
        frame: "window",
        width: 760,
        render: () => <GitAccessSection />,
      },
      {
        id: "live_access_servers",
        title: "Серверы: тип, свой центр, закрепление",
        note: "Список серверов с версиями; «Настроить» и «Добавить сервер» работают на демо-данных.",
        scenario: "servers_settings",
        frame: "window",
        width: 760,
        render: () => <GitAccessSection />,
      },
    ],
  },
];

/**
 * Живые записи: работают на демо-API, поэтому их можно пройти до конца
 * (ввести адрес, получить ключ, выбрать папку). В адрес можно вписать слова,
 * которыми демо выбирает исход: empty, plain, newer, notemplate, denied,
 * offline, tls, sso, limit, changed (для ssh: ключ сервера изменился).
 */
export const getRemoteLiveGallery = (): GalleryGroup[] => [
  ...accessLiveGroups(),
  {
    id: "live-connect",
    title: "Окно подключения (живое)",
    description:
      "Пройдите шаги сами. Слова в адресе задают исход проверки: denied, empty, plain, newer, notemplate, offline, tls, sso, limit, changed.",
    entries: [
      connectEntry(
        "live_connect_new",
        "Подключение с нуля",
        "Адрес, доступ, проверка, подключение; у демо уже есть автор версий.",
        "not_connected",
      ),
      connectEntry(
        "live_connect_warnings",
        "Подключение с предупреждениями",
        "NDA, LFS, облачная папка: каждое предупреждение требует решения.",
        "connect_warnings",
      ),
      connectEntry(
        "live_connect_large",
        "Подключение с крупными файлами",
        "Окно не даёт перейти дальше, пока файлы в истории больше лимита.",
        "connect_large_files",
      ),
      connectEntry(
        "live_connect_profile",
        "Подключение без автора версий",
        "Окно начинается с «Представься».",
        "connect_no_profile",
      ),
      connectEntry(
        "live_connect_fix",
        "Обновление доступа",
        "Шаг доступа для уже подключённого проекта с отказом.",
        "auth_failed",
        "fix_access",
      ),
    ],
  },
  {
    id: "live-clone",
    title: "Клонирование проекта (живое)",
    entries: [
      cloneEntry(
        "live_clone_empty",
        "Мастер с нуля",
        "Шаги: источник (адрес или файл bundle), папка, загрузка.",
        null,
      ),
      cloneEntry(
        "live_clone_ready",
        "Мастер с готовым адресом",
        "Адрес передан из окна подключения: проверка стартует сразу.",
        "https://github.com/hse-team/paper",
      ),
      cloneEntry(
        "live_clone_newer",
        "Проект от более новой Студии",
        "Итог проверки: откроется на чтение.",
        "https://github.com/hse-team/paper-newer",
      ),
      cloneEntry(
        "live_clone_plain",
        "Репозиторий не от Студии",
        "Итог проверки: клонировать нечего.",
        "https://github.com/hse-team/plain",
      ),
      cloneEntry(
        "live_clone_denied",
        "Доступ не принят",
        "Итог проверки: отказ с подсказкой.",
        "https://github.com/hse-team/paper-denied",
      ),
    ],
  },
  {
    id: "live-settings",
    title: "Настройки проекта: синхронизация (живые)",
    entries: [
      cardEntry(
        "live_card_connected",
        "Подключено",
        "Карточка репозитория: адрес, доступ, ветка, кнопки.",
        "up_to_date",
        "connection",
      ),
      cardEntry(
        "live_card_not_connected",
        "Не подключено",
        "Карточка зовёт подключить репозиторий.",
        "not_connected",
        "connection",
      ),
      cardEntry(
        "live_card_auth_failed",
        "Доступ не принят",
        "Красная заметка и «Заменить доступ».",
        "auth_failed",
        "connection",
      ),
      cardEntry(
        "live_card_fetch",
        "Автоматическая проверка",
        "Переключатель и выбор интервала.",
        "up_to_date",
        "fetch",
      ),
      cardEntry(
        "live_card_shared",
        "Папка в облачной синхронизации",
        "Предупреждение и подтверждение.",
        "shared_folder",
        "shared",
      ),
    ],
  },
  {
    id: "live-access",
    title: "Настройки приложения: доступ к репозиториям (живой)",
    entries: [
      {
        id: "live_access",
        title: "Токены, ключи, доверенные серверы, хранилище",
        note: "Заменить токен, удалить доступ, посмотреть, где хранятся секреты.",
        scenario: "shared_folder",
        frame: "window",
        width: 760,
        render: () => <GitAccessSection />,
      },
    ],
  },
];
