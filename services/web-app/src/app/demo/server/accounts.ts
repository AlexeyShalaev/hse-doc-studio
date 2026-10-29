import type {
  AccountProfile,
  AccountSession,
  SessionUser,
} from "@entities/session";

// Состояние аккаунта в демо-мире: профиль подписи и список сессий. Строится
// лениво для вошедшего человека и сбрасывается при смене пользователя.

export const DEMO_NOREPLY_DOMAIN = "noreply.studio.example.org";

export type DemoAccount = {
  profile: AccountProfile;
  sessions: AccountSession[];
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

export const createDemoAccount = (user: SessionUser): DemoAccount => {
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
