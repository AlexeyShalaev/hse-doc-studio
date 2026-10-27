import type { QueryClient } from "@tanstack/react-query";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import {
  gitRemoteKeys,
  type GitCredential,
  type GitHostSettings,
  type GitTokenInfo,
} from "@entities/git-remote";
import type { GitTlsCertificate } from "@entities/git-sync";
import type { TokenVerdict } from "../model/tokenVerdict";
import { AccessStep } from "../ui/AccessStep";
import { CredentialCard } from "../ui/CredentialCard";
import { ProviderChip } from "../ui/ProviderChip";
import { HostSettingsDialog } from "../ui/HostSettingsDialog";
import { ServersCard } from "../ui/ServersCard";
import { TlsTrustDialog } from "../ui/TlsTrustDialog";
import { TokenCheckCard } from "../ui/TokenCheckCard";
import { PAT } from "./connectFixtures";
import { noop, urlOf } from "./galleryKit";

// Записи галереи про серверы, токены и сертификаты: как выглядит выпуск токена
// у каждого вида сервера, каждый итог проверки токена, окна доверия к сертификату
// и раздел настроек «Серверы git». Живые варианты (на демо-данных)
// лежат в liveGallery.

const DAY = 24 * 60 * 60 * 1000;
const inDays = (days: number): string =>
  new Date(Date.now() + days * DAY).toISOString();

// --- серверы и ссылки на токены --------------------------------------------------

const hostSettings = (
  host: string,
  over: Partial<GitHostSettings> = {},
): GitHostSettings => ({
  host,
  port: null,
  provider_override: null,
  provider_info: { id: "gitlab", detected_by: "host", version: null },
  ca_present: false,
  pinned_fingerprint: null,
  ...over,
});

const providerEntry = (
  id: string,
  title: string,
  note: string,
  url: string,
  known: GitHostSettings[] = [],
  credentials: GitCredential[] = [],
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  seed: (client: QueryClient) => {
    client.setQueryData(gitRemoteKeys.hostSettings(), known);
  },
  render: () => (
    <div className="flex flex-col" style={{ gap: 12 }}>
      {/* Чип сервера живёт на шаге адреса; здесь он рядом, чтобы было видно, откуда ссылка. */}
      <ProviderChip url={urlOf(url)} />
      <AccessStep
        url={urlOf(url)}
        fixing={false}
        bound={null}
        credentials={credentials}
        isLoadingCredentials={false}
        secretsOk
        projectName="Курсовая работа"
        onContinue={noop}
        onBack={noop}
        onSwitchUrl={noop}
      />
    </div>
  ),
});

const providerEntries = (): GalleryEntry[] => [
  providerEntry(
    "provider_gitlab_com",
    "GitLab.com: токен по ссылке",
    "Чип «GitLab», кнопка «Создать токен на GitLab» с подставленными правами, три шага под ней.",
    "https://gitlab.com/hse-team/paper.git",
  ),
  providerEntry(
    "provider_gitlab_self",
    "Свой GitLab 17",
    "В чипе видна версия сервера; ссылка ведёт на страницу токенов этого сервера.",
    "https://gitlab.hse.ru/team/paper.git",
    [
      hostSettings("gitlab.hse.ru", {
        provider_info: { id: "gitlab", detected_by: "api", version: "17.3.1" },
      }),
    ],
  ),
  providerEntry(
    "provider_gitlab_old",
    "Старый GitLab 13: запасная ссылка",
    "Основная ссылка может не открыться на старой версии: рядом запасная, «страница не открылась?».",
    "https://gitlab.old.hse.ru/team/paper.git",
    [
      hostSettings("gitlab.old.hse.ru", {
        provider_info: { id: "gitlab", detected_by: "api", version: "13.12.2" },
      }),
    ],
  ),
  providerEntry(
    "provider_github",
    "GitHub: точный токен",
    "Ссылка с именем токена; под кнопкой напоминание выбрать только этот репозиторий.",
    "https://github.com/hse-team/paper.git",
  ),
  providerEntry(
    "provider_gitea",
    "Gitea и Codeberg: шаги без подстановки",
    "У сервера нет ссылки с подставленными правами: страница настроек и нумерованные шаги.",
    "https://codeberg.org/anna/paper.git",
  ),
  providerEntry(
    "provider_bitbucket",
    "Bitbucket: шаги без подстановки",
    "Токен репозитория или рабочей области; нумерованные шаги.",
    "https://bitbucket.org/hse-team/paper.git",
  ),
  providerEntry(
    "provider_api_detect",
    "Тип узнан по ответу сервера",
    "По имени хоста тип не понять: сервер назвал себя GitLab 16, в чипе пометка «по ответу сервера».",
    "https://forge.hse.ru/team/paper.git",
    [
      hostSettings("forge.hse.ru", {
        provider_info: { id: "gitlab", detected_by: "api", version: "16.11.2" },
      }),
    ],
  ),
  providerEntry(
    "provider_override",
    "Тип выбран человеком",
    "Автоопределение ошиблось, тип поправлен вручную и запомнен для этого сервера.",
    "https://git.hse.ru/team/paper.git",
    [
      hostSettings("git.hse.ru", {
        provider_override: "gitea",
        provider_info: { id: "gitea", detected_by: "override", version: null },
      }),
    ],
  ),
  providerEntry(
    "provider_unknown",
    "Сервер не узнан",
    "Тип не определён: чип предлагает выбрать сервер, ссылки на токен нет, есть общие шаги.",
    "https://git.example.com/team/paper.git",
    [
      hostSettings("git.example.com", {
        provider_info: { id: "other", detected_by: "unknown", version: null },
      }),
    ],
  ),
];

// --- итог проверки токена --------------------------------------------------------

const TOKEN_INFO: GitTokenInfo = {
  login: "anna.petrova",
  scopes: ["read_repository", "write_repository"],
  expires_at: inDays(62),
  sufficiency: "sufficient",
  missing: [],
};

const GITLAB_LINK =
  "https://gitlab.hse.ru/-/user_settings/personal_access_tokens?name=HSE+Studio&scopes=read_repository,write_repository";

const checkCard = (
  id: string,
  title: string,
  note: string,
  verdict: TokenVerdict | null,
  props: Partial<React.ComponentProps<typeof TokenCheckCard>> = {},
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  width: 560,
  render: () => (
    <TokenCheckCard
      verdict={verdict}
      provider="gitlab"
      version="17.3.1"
      createUrl={GITLAB_LINK}
      onRetry={noop}
      onReviewCertificate={noop}
      {...props}
    />
  ),
});

const errorVerdict = (
  code: string,
  detail: string,
  extra: Partial<Extract<TokenVerdict, { kind: "error" }>> = {},
): TokenVerdict => ({
  kind: "error",
  code,
  detail,
  certificate: null,
  expected: null,
  actual: null,
  info: null,
  ...extra,
});

const GALLERY_CERT: GitTlsCertificate = {
  fingerprint_sha256: "SHA256:b1Kq0vU7m4Zl9Xc2Tn8RjHf3eWyAo5DsPi6GgLxEu0w",
  subject: "CN=gitlab.hse.local",
  issuer: "CN=HSE Internal CA",
  not_before: "2026-01-10T00:00:00Z",
  not_after: "2027-01-10T00:00:00Z",
  self_signed: false,
};

const SELF_SIGNED: GitTlsCertificate = {
  fingerprint_sha256:
    "SHA256:s3lfS1gnedDemoCertificateFingerprint0123456789abcd",
  subject: "CN=gitlab.lab.local",
  issuer: "CN=gitlab.lab.local",
  not_before: "2026-03-01T00:00:00Z",
  not_after: "2028-03-01T00:00:00Z",
  self_signed: true,
};

const PIN_OLD = "SHA256:0ldPinnedCertificateFingerprintNoLongerPresented123";
const PIN_NEW = "SHA256:Zr3Vn8Hq1Lw6Ys0Ud4Cx9TkPb2Ea7MgFj5RiOtNo1Ae";

const checkEntries = (): GalleryEntry[] => [
  checkCard(
    "token_check_running",
    "Проверка токена идёт",
    "Круг загрузки и пояснение, итога пока нет.",
    null,
  ),
  checkCard(
    "token_check_sufficient",
    "Токен подходит",
    "Чей токен, какие у него права и сколько ему осталось.",
    { kind: "sufficient", info: TOKEN_INFO },
  ),
  checkCard(
    "token_check_narrow",
    "Токену не хватает прав",
    "Названо, какое право добавить (write_repository), и есть кнопка выпустить новый токен.",
    {
      kind: "too_narrow",
      info: {
        ...TOKEN_INFO,
        scopes: ["read_repository"],
        sufficiency: "too_narrow",
        missing: ["write_repository"],
      },
    },
  ),
  checkCard(
    "token_check_broad",
    "У токена слишком много прав",
    "Предупреждение (не отказ): лишнее право api называется явно.",
    {
      kind: "too_broad",
      info: {
        ...TOKEN_INFO,
        scopes: ["api"],
        sufficiency: "too_broad",
      },
    },
  ),
  checkCard(
    "token_check_unknown",
    "Права проверить нельзя",
    "Старый сервер или точный токен: не отказ, подключение проверит доступ само.",
    {
      kind: "unknown",
      info: {
        login: null,
        scopes: [],
        expires_at: null,
        sufficiency: "unknown",
        missing: [],
      },
    },
    { provider: "github", version: null },
  ),
  checkCard(
    "token_check_expired",
    "Срок токена истёк",
    "Дата, когда токен истёк, и ссылка на выпуск нового.",
    {
      kind: "expired",
      info: {
        login: null,
        scopes: [],
        expires_at: inDays(-6),
        sufficiency: "unknown",
        missing: [],
      },
    },
  ),
  checkCard(
    "token_check_auth_failed",
    "Сервер не принял токен",
    "Токен отозван или набран неверно.",
    errorVerdict("auth_failed", "Сервер отклонил токен."),
  ),
  checkCard(
    "token_check_tls_untrusted",
    "Сертификат сервера не из известного центра",
    "Проверка остановлена; кнопка «Проверить сертификат» открывает окно доверия.",
    errorVerdict("tls_untrusted_ca", "Сертификат выдан неизвестным центром.", {
      certificate: GALLERY_CERT,
    }),
  ),
  checkCard(
    "token_check_tls_pin",
    "Сертификат сервера изменился",
    "Раньше закреплён другой отпечаток; кнопка ведёт в окно сравнения.",
    errorVerdict(
      "tls_pin_mismatch",
      "Сертификат не совпадает с закреплённым.",
      {
        expected: PIN_OLD,
        actual: PIN_NEW,
      },
    ),
  ),
  checkCard(
    "token_check_offline",
    "Сервер недоступен",
    "Сети нет или сервер не отвечает; можно повторить проверку.",
    errorVerdict("offline", "Нет связи с сервером."),
  ),
];

// --- окна доверия к сертификату ---------------------------------------------------

const tlsEntry = (
  id: string,
  title: string,
  note: string,
  props: Omit<
    React.ComponentProps<typeof TlsTrustDialog>,
    "isOpen" | "onTrusted" | "onClose" | "host" | "port"
  >,
  host = "gitlab.hse.local",
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "plain",
  render: () => (
    <DialogLauncher label="Открыть окно">
      {({ isOpen, close }) => (
        <TlsTrustDialog
          isOpen={isOpen}
          host={host}
          port={null}
          onTrusted={close}
          onClose={close}
          {...props}
        />
      )}
    </DialogLauncher>
  ),
});

const tlsEntries = (): GalleryEntry[] => [
  tlsEntry(
    "tls_untrusted_ca",
    "Сертификат организации: добавить центр выдачи",
    "Вставить текст сертификата центра или выбрать файл; проверку отключить нельзя. Без сервера сохранение покажет отказ, до конца это проходится в живых записях.",
    { mode: "untrusted", certificate: GALLERY_CERT },
  ),
  tlsEntry(
    "tls_self_signed",
    "Самоподписанный сертификат: закрепить отпечаток",
    "Сразу открыта вкладка закрепления: кому выдан, срок, отпечаток и отметка «я сверил(а)».",
    { mode: "untrusted", certificate: SELF_SIGNED },
    "gitlab.lab.local",
  ),
  tlsEntry(
    "tls_no_certificate",
    "Сервер не прислал сертификат",
    "Закрепить нечего: объяснено, что нужно повторить проверку.",
    { mode: "untrusted", certificate: null },
  ),
  tlsEntry(
    "tls_pin_mismatch",
    "Сертификат изменился после закрепления",
    "Красное предупреждение, оба отпечатка рядом и ввод имени сервера, чтобы закрепить новый.",
    {
      mode: "pin_mismatch",
      certificate: null,
      expected: PIN_OLD,
      actual: PIN_NEW,
    },
  ),
];

// --- раздел «Серверы git» ----------------------------------------------------------

const cred = (over: Partial<GitCredential>): GitCredential => ({
  ...PAT,
  public_key: null,
  fingerprint_sha256: null,
  used_by: [],
  last_used_at: null,
  ...over,
});

const SERVER_ROWS: GitHostSettings[] = [
  hostSettings("gitlab.com", {
    provider_info: { id: "gitlab", detected_by: "host", version: null },
  }),
  hostSettings("gitlab.hse.ru", {
    provider_info: { id: "gitlab", detected_by: "api", version: "17.3.1" },
  }),
  hostSettings("gitlab.hse.local", {
    port: 8443,
    ca_present: true,
    provider_info: { id: "gitlab", detected_by: "api", version: "17.3.1" },
  }),
  hostSettings("gitlab.lab.local", {
    pinned_fingerprint: SELF_SIGNED.fingerprint_sha256,
  }),
  hostSettings("git.hse.ru", {
    provider_override: "gitea",
    provider_info: { id: "gitea", detected_by: "override", version: null },
  }),
];

const SERVER_CREDENTIALS: GitCredential[] = [
  cred({
    id: "srv-1",
    label: "GitLab ВШЭ, на 90 дней",
    host: "gitlab.hse.ru",
    token_family: "glpat",
    status: "ok",
    expires_at: inDays(5),
  }),
  cred({
    id: "srv-2",
    label: "GitLab ВШЭ, запасной",
    host: "gitlab.hse.ru",
    token_family: "glpat",
    status: "ok",
    expires_at: inDays(200),
  }),
  cred({
    id: "srv-3",
    label: "Внутренний GitLab",
    host: "gitlab.hse.local",
    token_family: "glpat",
    status: "ok",
    expires_at: null,
  }),
  cred({
    id: "srv-4",
    label: "Лаборатория",
    host: "gitlab.lab.local",
    token_family: "glpat",
    status: "auth_failed",
    expires_at: inDays(-3),
  }),
];

const serversEntry = (
  id: string,
  title: string,
  note: string,
  settings: GitHostSettings[],
  credentials: GitCredential[],
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  width: 720,
  seed: (client: QueryClient) => {
    client.setQueryData(gitRemoteKeys.hostSettings(), settings);
    client.setQueryData(gitRemoteKeys.credentials(), credentials);
  },
  render: () => <ServersCard settings={settings} credentials={credentials} />,
});

const serverEntries = (): GalleryEntry[] => [
  serversEntry(
    "servers_empty",
    "Серверов пока нет",
    "Пояснение и кнопка «Добавить сервер».",
    [],
    [],
  ),
  serversEntry(
    "servers_list",
    "Список серверов",
    "Тип и версия, как определён, свой центр выдачи, закреплённый сертификат и доступы со сроками.",
    SERVER_ROWS,
    SERVER_CREDENTIALS,
  ),
  {
    id: "server_dialog_edit",
    title: "Настройка сервера",
    note: "Тип сервера, сертификат центра выдачи (вставить или выбрать файл), снятие закрепления. Без сервера сохранение покажет отказ.",
    frame: "plain",
    seed: (client: QueryClient) => {
      client.setQueryData(gitRemoteKeys.hostSettings(), SERVER_ROWS);
    },
    render: () => (
      <DialogLauncher label="Открыть окно">
        {({ isOpen, close }) =>
          isOpen ? (
            <HostSettingsDialog
              settings={SERVER_ROWS[3] ?? null}
              onClose={close}
            />
          ) : null
        }
      </DialogLauncher>
    ),
  },
  {
    id: "server_dialog_add",
    title: "Добавить сервер заранее",
    note: "Адрес сервера, тип и сертификат центра до первого подключения.",
    frame: "plain",
    render: () => (
      <DialogLauncher label="Открыть окно">
        {({ isOpen, close }) =>
          isOpen ? <HostSettingsDialog settings={null} onClose={close} /> : null
        }
      </DialogLauncher>
    ),
  },
];

// --- карточки доступов со сроками ---------------------------------------------------

const credentialEntry = (
  id: string,
  title: string,
  note: string,
  credential: GitCredential,
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  width: 640,
  seed: (client: QueryClient) => {
    client.setQueryData(gitRemoteKeys.hostSettings(), SERVER_ROWS);
    client.setQueryData(gitRemoteKeys.credentials(), [credential]);
  },
  render: () => <CredentialCard credential={credential} />,
});

const credentialEntries = (): GalleryEntry[] => [
  credentialEntry(
    "credential_ok",
    "Токен без замечаний",
    "Срок далеко: дата серым текстом, кнопка «Проверить» у токена.",
    cred({
      id: "c-ok",
      label: "GitLab ВШЭ",
      host: "gitlab.hse.ru",
      token_family: "glpat",
      status: "ok",
      expires_at: inDays(120),
      last_used_at: inDays(-1),
    }),
  ),
  credentialEntry(
    "credential_soon",
    "Срок скоро выйдет",
    "Жёлтая плашка «истекает через N дней» и подсвеченная «Заменить токен».",
    cred({
      id: "c-soon",
      label: "GitLab ВШЭ, на 90 дней",
      host: "gitlab.hse.ru",
      token_family: "glpat",
      status: "ok",
      expires_at: inDays(5),
    }),
  ),
  credentialEntry(
    "credential_expired",
    "Срок вышел",
    "Красная плашка «истёк N дней назад»; замена подсвечена.",
    cred({
      id: "c-expired",
      label: "Лаборатория",
      host: "gitlab.lab.local",
      token_family: "glpat",
      status: "auth_failed",
      expires_at: inDays(-3),
    }),
  ),
  credentialEntry(
    "credential_no_expiry",
    "Токен без срока",
    "Срока нет: плашки нет, дата не показывается.",
    cred({
      id: "c-none",
      label: "Gitea, учебный",
      host: "codeberg.org",
      status: "unverified",
      expires_at: null,
    }),
  ),
];

/** Серверы, ссылки на токены, итоги проверки токена, окна сертификата и раздел серверов. */
export const getRemoteAccessStaticGallery = (): GalleryGroup[] => [
  {
    id: "access-providers",
    title: "Токен у разных серверов",
    description:
      "Шаг «Доступ» для GitLab.com, своего GitLab (с версией и запасной ссылкой), GitHub, Gitea, Bitbucket и неузнанного сервера.",
    entries: providerEntries(),
  },
  {
    id: "access-token-check",
    title: "Итог проверки токена",
    entries: checkEntries(),
  },
  {
    id: "access-tls",
    title: "Недоверенный сертификат сервера",
    description:
      "Проверка сертификата не отключается: человек добавляет центр выдачи или закрепляет отпечаток.",
    entries: tlsEntries(),
  },
  {
    id: "access-servers",
    title: "Настройки: серверы git",
    entries: serverEntries(),
  },
  {
    id: "access-credentials",
    title: "Настройки: сроки токенов",
    entries: credentialEntries(),
  },
];
