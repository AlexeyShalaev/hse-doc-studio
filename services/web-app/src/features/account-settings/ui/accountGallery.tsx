import type {
  AccountProfile,
  AccountSession,
  ApiToken,
} from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { CommitIdentityCard } from "./CommitIdentityCard";
import { AccountSection } from "./AccountSection";
import { PasswordCard } from "./PasswordCard";
import { ProfileCard } from "./ProfileCard";
import type { IdentityRow } from "../lib/identityRows";
import { IdentitiesCard } from "./IdentitiesCard";
import { SessionsCard } from "./SessionsCard";
import { TokensCard } from "./TokensCard";

const W = 560;
const noop = () => undefined;

const PROFILE: AccountProfile = {
  id: "u_01hx7k2m9c",
  name: "Анна Петрова",
  email: "anna.petrova@example.org",
  locale: "ru",
  commit_name: null,
  commit_email: null,
  commit_use_account_email: false,
  effective_commit_name: "Анна Петрова",
  effective_commit_email: "u_01hx7k2m9c@noreply.studio.example.org",
  commit_email_is_noreply: true,
};

const OWN: AccountProfile = {
  ...PROFILE,
  commit_name: "Anna P.",
  commit_email: "anna@personal.example.com",
  effective_commit_name: "Anna P.",
  effective_commit_email: "anna@personal.example.com",
  commit_email_is_noreply: false,
};

const ACCOUNT_EMAIL: AccountProfile = {
  ...PROFILE,
  commit_use_account_email: true,
  effective_commit_email: PROFILE.email,
  commit_email_is_noreply: false,
};

const SESSIONS: AccountSession[] = [
  {
    id: "ses_01hx8a",
    created_at: "2026-10-20T08:14:03Z",
    last_seen_at: new Date().toISOString(),
    ip: "203.0.113.24",
    user_agent: "Firefox 131 на macOS",
    current: true,
  },
  {
    id: "ses_01hx7q",
    created_at: "2026-10-12T17:02:44Z",
    last_seen_at: "2026-10-19T11:30:00Z",
    ip: null,
    user_agent: "Chrome 130 на Windows",
    current: false,
  },
  {
    id: "ses_01hx7r",
    created_at: "2026-10-22T09:00:00Z",
    last_seen_at: "2026-10-27T07:00:00Z",
    ip: "198.51.100.7",
    user_agent: "Safari 18 на iPhone",
    current: false,
  },
];

const TOKENS: ApiToken[] = [
  {
    id: "pat_01hx9b",
    name: "CLI на ноутбуке",
    prefix: "hsd_pat_4Kq",
    scopes: ["api", "git:read"],
    created_at: "2026-10-21T12:00:00Z",
    expires_at: "2099-01-21T12:00:00Z",
    last_used_at: null,
  },
  {
    id: "pat_01hx9c",
    name: "CI только чтение",
    prefix: "hsd_pat_9Zr",
    scopes: ["git:read"],
    created_at: "2026-09-01T09:00:00Z",
    expires_at: null,
    last_used_at: "2026-10-26T22:15:00Z",
  },
  {
    id: "pat_01hx8z",
    name: "Старый скрипт",
    prefix: "hsd_pat_Lm2",
    scopes: ["api", "git:write"],
    created_at: "2025-03-01T09:00:00Z",
    expires_at: "2025-09-01T09:00:00Z",
    last_used_at: "2025-08-30T10:00:00Z",
  },
];

const PASSWORD_IDENTITY: IdentityRow = {
  id: "idn_password",
  kind: "password",
  provider_id: null,
  provider_label: "",
  email: "anna.petrova@example.org",
  email_verified: null,
  can_unlink: false,
};

const SSO_IDENTITY: IdentityRow = {
  id: "idn_keycloak",
  kind: "oidc",
  provider_id: "keycloak",
  provider_label: "HSE SSO",
  email: "anna.petrova@hse.ru",
  email_verified: true,
  can_unlink: true,
};

const PROVIDERS = [
  { id: "keycloak", label: "HSE SSO" },
  { id: "google", label: "Google" },
];

const tokens = (extra: Partial<Parameters<typeof TokensCard>[0]> = {}) => (
  <TokensCard
    status="ready"
    tokens={TOKENS}
    onCreate={noop}
    onRevoke={noop}
    {...extra}
  />
);

const identities = (
  extra: Partial<Parameters<typeof IdentitiesCard>[0]> = {},
) => (
  <IdentitiesCard
    status="ready"
    identities={[PASSWORD_IDENTITY, SSO_IDENTITY]}
    providers={PROVIDERS}
    onLink={noop}
    onUnlink={noop}
    {...extra}
  />
);

const entry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({ id, title, frame: "window", width: W, render, ...extra });

const profileCard = (
  extra: Partial<Parameters<typeof ProfileCard>[0]> = {},
) => (
  <ProfileCard
    profile={PROFILE}
    emailVerified
    onSave={noop}
    email={{ onSubmit: noop }}
    {...extra}
  />
);

const password = (extra: Partial<Parameters<typeof PasswordCard>[0]> = {}) => (
  <PasswordCard minLength={10} onSubmit={noop} {...extra} />
);

const commit = (
  profile: AccountProfile,
  extra: Partial<Parameters<typeof CommitIdentityCard>[0]> = {},
) => <CommitIdentityCard profile={profile} onSave={noop} {...extra} />;

const sessions = (extra: Partial<Parameters<typeof SessionsCard>[0]> = {}) => (
  <SessionsCard
    status="ready"
    sessions={SESSIONS}
    onRevoke={noop}
    onRevokeOthers={noop}
    {...extra}
  />
);

/** Настройки аккаунта серверного режима: все карточки и их состояния. */
export const getAccountSettingsGallery = (): GalleryGroup[] => [
  {
    id: "account-profile",
    title: "Аккаунт: имя и почта",
    entries: [
      entry("account_profile", "Имя и подтверждённая почта", () =>
        profileCard(),
      ),
      entry(
        "account_profile_unverified",
        "Почта не подтверждена",
        () => profileCard({ emailVerified: false }),
        { note: "Рядом с адресом предупреждение." },
      ),
      entry("account_profile_saving", "Имя сохраняется", () =>
        profileCard({ pending: true }),
      ),
      entry("account_profile_issue", "Сервер отклонил имя", () =>
        profileCard({ nameIssue: "Имя длиннее 128 символов." }),
      ),
      entry("account_profile_failed", "Сохранить не вышло", () =>
        profileCard({ failure: { code: "network" } }),
      ),
      entry("account_email_sent", "Письмо на новый адрес ушло", () =>
        profileCard({
          email: {
            onSubmit: noop,
            result: { status: "check_email", link: null },
          },
        }),
      ),
    ],
  },
  {
    id: "account-password",
    title: "Аккаунт: пароль",
    entries: [
      entry("account_password", "Форма", () => password()),
      entry("account_password_pending", "Пароль меняется", () =>
        password({ pending: true }),
      ),
      entry("account_password_wrong", "Текущий пароль неверный", () =>
        password({ failure: { code: "invalid_credentials" } }),
      ),
      entry("account_password_policy", "Новый пароль не прошёл политику", () =>
        password({ failure: { code: "password_policy" } }),
      ),
      entry("account_password_limited", "Слишком много попыток", () =>
        password({ failure: { code: "rate_limited" } }),
      ),
      entry("account_password_done", "Пароль сменён", () =>
        password({ done: true }),
      ),
      entry(
        "account_password_sso",
        "Вход только через SSO",
        () => password({ passwordEnabled: false }),
        { note: "Пароля у аккаунта нет, форма заменена пояснением." },
      ),
    ],
  },
  {
    id: "account-commit",
    title: "Аккаунт: подпись версий",
    description:
      "Коммит остаётся во внешнем репозитории навсегда, поэтому настоящий адрес уходит туда только по выбору человека.",
    entries: [
      entry("account_commit_noreply", "Адрес по умолчанию (noreply)", () =>
        commit(PROFILE),
      ),
      entry("account_commit_account", "E-mail аккаунта", () =>
        commit(ACCOUNT_EMAIL),
      ),
      entry("account_commit_own", "Свой адрес", () => commit(OWN)),
      entry("account_commit_saving", "Сохраняется", () =>
        commit(OWN, { pending: true }),
      ),
      entry("account_commit_issue", "Сервер отклонил адрес", () =>
        commit(OWN, {
          issues: { commit_email: "Это не похоже на адрес почты." },
        }),
      ),
      entry("account_commit_saved", "Сохранено", () =>
        commit(PROFILE, { saved: true }),
      ),
    ],
  },
  {
    id: "account-sessions",
    title: "Аккаунт: сессии",
    entries: [
      entry("account_sessions", "Несколько устройств", () => sessions()),
      entry(
        "account_sessions_alone",
        "Только эта сессия",
        () => sessions({ sessions: SESSIONS.slice(0, 1) }),
        { note: "Завершать нечего: кнопки «Завершить остальные» нет." },
      ),
      entry("account_sessions_busy", "Идёт завершение", () =>
        sessions({ revokingId: "ses_01hx7q" }),
      ),
      entry("account_sessions_failed", "Завершить не вышло", () =>
        sessions({ failure: { code: "network" } }),
      ),
      entry("account_sessions_loading", "Загрузка", () =>
        sessions({ status: "loading", sessions: [] }),
      ),
      entry("account_sessions_error", "Не загрузились", () =>
        sessions({ status: "error", sessions: [], onRetry: noop }),
      ),
    ],
  },
  {
    id: "account-tokens",
    title: "Аккаунт: токены доступа",
    description:
      "Значение токена показывается один раз, сразу после создания. В списке остаётся только начало.",
    entries: [
      entry("account_tokens", "Несколько токенов", () => tokens(), {
        note: "У последнего срок истёк: он помечен и всё равно отзывается.",
      }),
      entry("account_tokens_empty", "Токенов нет", () =>
        tokens({ tokens: [] }),
      ),
      entry("account_tokens_form", "Форма создания", () =>
        tokens({ startOpen: true }),
      ),
      entry("account_tokens_creating", "Токен создаётся", () =>
        tokens({ startOpen: true, creating: true }),
      ),
      entry("account_tokens_limited", "Слишком много попыток", () =>
        tokens({ startOpen: true, createFailure: { code: "rate_limited" } }),
      ),
      entry(
        "account_tokens_created",
        "Токен создан",
        () =>
          tokens({
            created: {
              token: "hsd_pat_4KqVn8Zc1QwTy5LbKdPm2RxJ7sEa3HuF",
              name: "CLI на ноутбуке",
            },
          }),
        { note: "Единственный момент, когда токен виден целиком." },
      ),
      entry("account_tokens_busy", "Идёт отзыв", () =>
        tokens({ revokingId: "pat_01hx9b" }),
      ),
      entry("account_tokens_failed", "Отозвать не вышло", () =>
        tokens({ failure: { code: "network" } }),
      ),
      entry("account_tokens_loading", "Загрузка", () =>
        tokens({ status: "loading", tokens: [] }),
      ),
      entry("account_tokens_error", "Не загрузились", () =>
        tokens({ status: "error", tokens: [], onRetry: noop }),
      ),
    ],
  },
  {
    id: "account-identities",
    title: "Аккаунт: способы входа",
    description:
      "Последний способ входа отвязать нельзя: у него вместо кнопки пояснение.",
    entries: [
      entry("account_identities", "Пароль и SSO", () => identities()),
      entry(
        "account_identities_sole_sso",
        "Только SSO",
        () =>
          identities({
            identities: [{ ...SSO_IDENTITY, can_unlink: false }],
          }),
        { note: "Единственный способ входа защищён." },
      ),
      entry("account_identities_sole_password", "Только пароль", () =>
        identities({ identities: [PASSWORD_IDENTITY] }),
      ),
      entry("account_identities_all_linked", "Привязаны все провайдеры", () =>
        identities({ providers: PROVIDERS.slice(0, 1) }),
      ),
      entry("account_identities_linking", "Переход к провайдеру", () =>
        identities({ linkingId: "google" }),
      ),
      entry("account_identities_busy", "Идёт отвязка", () =>
        identities({ unlinkingId: "idn_01hx9d" }),
      ),
      entry("account_identities_last", "Сервер не дал убрать последний", () =>
        identities({ failure: { code: "last_login_method" } }),
      ),
      entry("account_identities_failed", "Привязать не вышло", () =>
        identities({ failure: { code: "network" } }),
      ),
      entry("account_identities_loading", "Загрузка", () =>
        identities({ status: "loading", identities: [] }),
      ),
      entry("account_identities_error", "Не загрузились", () =>
        identities({ status: "error", identities: [], onRetry: noop }),
      ),
    ],
  },
  {
    id: "account-live",
    title: "Аккаунт: живой раздел",
    description:
      "На демо-мире. Текущий пароль, начинающийся с wrong, даёт отказ; пароль password… не проходит политику. Без почты ссылка смены адреса показывается на экране.",
    entries: [
      entry("account_live", "Студент", () => <AccountSection />, {
        scenario: "student_ready",
      }),
      entry(
        "account_live_nosmtp",
        "Студент, почта не настроена",
        () => <AccountSection />,
        {
          scenario: "student_nosmtp",
        },
      ),
      entry(
        "account_live_linked",
        "Студент, пароль и SSO",
        () => <AccountSection />,
        { scenario: "student_linked" },
      ),
      entry(
        "account_live_sso",
        "Студент, вход через SSO",
        () => <AccountSection />,
        {
          scenario: "student_sso",
        },
      ),
    ],
  },
];
