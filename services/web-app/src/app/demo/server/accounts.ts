import type {
  AccountIdentity,
  AccountProfile,
  AccountSession,
  ApiToken,
  AuthOptions,
  SessionUser,
} from "@entities/session";

// Состояние аккаунта в демо-мире: профиль подписи и список сессий. Строится
// лениво для вошедшего человека и сбрасывается при смене пользователя.

export const DEMO_NOREPLY_DOMAIN = "noreply.studio.example.org";

export type DemoAccount = {
  profile: AccountProfile;
  sessions: AccountSession[];
  /** Личные токены доступа. */
  tokens: ApiToken[];
  /** Привязанные внешние входы; пароль сервер среди них не отдаёт. */
  identities: AccountIdentity[];
};

const NOW = Date.parse("2026-10-28T09:00:00Z");
const ago = (hours: number): string =>
  new Date(NOW - hours * 3_600_000).toISOString().replace(".000Z", "Z");

export const effectiveOf = (
  profile: Pick<
    AccountProfile,
    | "id"
    | "name"
    | "email"
    | "commit_name"
    | "commit_email"
    | "commit_use_account_email"
  >,
): Pick<
  AccountProfile,
  "effective_commit_name" | "effective_commit_email" | "commit_email_is_noreply"
> => {
  const name = profile.commit_name ?? profile.name;
  if (profile.commit_email !== null) {
    return {
      effective_commit_name: name,
      effective_commit_email: profile.commit_email,
      commit_email_is_noreply: false,
    };
  }
  if (profile.commit_use_account_email) {
    return {
      effective_commit_name: name,
      effective_commit_email: profile.email,
      commit_email_is_noreply: false,
    };
  }
  return {
    effective_commit_name: name,
    effective_commit_email: `${profile.id}@${DEMO_NOREPLY_DOMAIN}`,
    commit_email_is_noreply: true,
  };
};

const seedIdentities = (
  user: SessionUser,
  auth: AuthOptions,
): AccountIdentity[] => {
  // Первый провайдер уже привязан: без пароля это единственный способ входа.
  const first = auth.oidc_providers[0];
  if (!first) return [];
  return [
    {
      provider: first.id,
      label: first.label,
      email: user.email.replace(/@.*/, "@hse.ru"),
      email_verified: true,
    },
  ];
};

const seedTokens = (): ApiToken[] => [
  {
    id: "pat_01hxdv",
    name: "Студия на MacBook Анны",
    prefix: "hsd_pat_7Rm",
    scopes: ["git:read", "git:write"],
    created_at: ago(24 * 3),
    expires_at: ago(-24 * 87),
    last_used_at: ago(2),
    origin: "device",
    client_name: "Студия на MacBook Анны",
    client_kind: "desktop",
  },
  {
    id: "pat_01hx9b",
    name: "CLI на ноутбуке",
    prefix: "hsd_pat_4Kq",
    scopes: ["api", "git:read"],
    created_at: ago(24 * 7),
    expires_at: ago(-24 * 83),
    last_used_at: null,
    origin: "manual",
    client_name: null,
    client_kind: null,
  },
  {
    id: "pat_01hx9c",
    name: "CI только чтение",
    prefix: "hsd_pat_9Zr",
    scopes: ["git:read"],
    created_at: ago(24 * 60),
    expires_at: null,
    last_used_at: ago(30),
    origin: "manual",
    client_name: null,
    client_kind: null,
  },
  {
    id: "pat_01hx8z",
    name: "Старый скрипт",
    prefix: "hsd_pat_Lm2",
    scopes: ["api"],
    created_at: ago(24 * 200),
    expires_at: ago(24 * 20),
    last_used_at: ago(24 * 40),
    origin: "manual",
    client_name: null,
    client_kind: null,
  },
];

export const createDemoAccount = (
  user: SessionUser,
  auth: AuthOptions,
): DemoAccount => {
  const base = {
    id: user.id,
    name: user.name,
    email: user.email,
    locale: user.locale,
    commit_name: null,
    commit_email: null,
    commit_use_account_email: false,
  };
  return {
    profile: { ...base, ...effectiveOf(base) },
    tokens: seedTokens(),
    identities: seedIdentities(user, auth),
    sessions: [
      {
        id: "ses_demo_current",
        created_at: ago(30),
        last_seen_at: ago(0.02),
        ip: "203.0.113.24",
        user_agent: "Firefox 131 на macOS",
        current: true,
      },
      {
        id: "ses_demo_phone",
        created_at: ago(24 * 6),
        last_seen_at: ago(5),
        ip: "198.51.100.7",
        user_agent: "Safari 18 на iPhone",
        current: false,
      },
      {
        id: "ses_demo_office",
        created_at: ago(24 * 16),
        last_seen_at: ago(24 * 9),
        ip: null,
        user_agent: "Chrome 130 на Windows",
        current: false,
      },
    ],
  };
};
