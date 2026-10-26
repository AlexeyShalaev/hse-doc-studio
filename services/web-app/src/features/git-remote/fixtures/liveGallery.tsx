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
): GalleryEntry => ({
  id,
  title,
  note,
  scenario,
  frame: "plain",
  render: () => <ConnectLauncher mode={mode} />,
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

/**
 * Живые записи: работают на демо-API, поэтому их можно пройти до конца
 * (ввести адрес, получить ключ, выбрать папку). В адрес можно вписать слова,
 * которыми демо выбирает исход: empty, plain, newer, notemplate, denied,
 * offline, tls, sso, limit, changed (для ssh: ключ сервера изменился).
 */
export const getRemoteLiveGallery = (): GalleryGroup[] => [
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
