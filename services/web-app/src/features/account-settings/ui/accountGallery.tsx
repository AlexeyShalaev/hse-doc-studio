import type { AccountProfile, AccountSession } from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { CommitIdentityCard } from "./CommitIdentityCard";
import { AccountSection } from "./AccountSection";
import { PasswordCard } from "./PasswordCard";
import { ProfileCard } from "./ProfileCard";
import { SessionsCard } from "./SessionsCard";

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
