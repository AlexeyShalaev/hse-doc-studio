import {
  demoError,
  demoJson,
  demoNoContent,
  queryString,
} from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type {
  GitProjectPage,
  GitServerItem,
  GitServerLogin,
} from "@entities/git-server";

// Локальная Студия и сервер HSE Doc Studio в демо (раздел 10.13): подключённые
// серверы, вход кодом (подтверждается сам через несколько секунд) и проекты
// сервера. Особые адреса: `denied.example.org` даёт отказ на сайте,
// `other.example.org` не Студия, `down.example.org` не отвечает.

const APPROVE_AFTER_MS = 4000;

type DemoLogin = GitServerLogin & { startedAt: number };

const seedServers = (): GitServerItem[] => [
  {
    credential_id: "cred_studio_ok",
    server_url: "https://studio.example.org",
    host: "studio.example.org",
    account_name: "Анна Петрова",
    scopes: ["git:read", "git:write"],
    expires_at: "2027-01-30T09:00:00Z",
    state: "ok",
  },
  {
    credential_id: "cred_studio_revoked",
    server_url: "https://studio.hse.ru",
    host: "studio.hse.ru",
    account_name: null,
    scopes: [],
    expires_at: "2026-12-30T09:00:00Z",
    state: "revoked",
  },
];

const PROJECTS: GitProjectPage = {
  items: [
    {
      id: "5b0c1d2e-3f40-4152-8364-758697a8b9c0",
      name: "ВКР: Анализ требований",
      owner_name: "Анна Петрова",
      role: "owner",
      can_push: true,
      clone_url:
        "https://studio.example.org/git/5b0c1d2e-3f40-4152-8364-758697a8b9c0.git",
      updated_at: "2026-11-01T09:00:00Z",
    },
    {
      id: "6c1d2e3f-4051-4263-9475-8697a8b9c0d1",
      name: "Курсовой проект",
      owner_name: "МСПИН",
      role: "reviewer",
      can_push: false,
      clone_url:
        "https://studio.example.org/git/6c1d2e3f-4051-4263-9475-8697a8b9c0d1.git",
      updated_at: "2026-10-30T09:00:00Z",
    },
  ],
  total: 2,
  limit: 50,
  offset: 0,
};

let servers = seedServers();
const logins = new Map<string, DemoLogin>();
let sequence = 0;

/** Сброс состояния демо (галерея и тесты). */
export const resetGitServersDemo = (): void => {
  servers = seedServers();
  logins.clear();
  sequence = 0;
};

const hostOf = (raw: string): string | null => {
  try {
    const url = new URL(raw.trim());
    return url.protocol === "https:" || url.hostname === "localhost"
      ? url.hostname
      : null;
  } catch {
    return null;
  }
};

const publicLogin = ({ startedAt: _at, ...rest }: DemoLogin): GitServerLogin =>
  rest;

const advance = (login: DemoLogin): GitServerLogin => {
  if (
    login.state !== "pending" ||
    Date.now() - login.startedAt < APPROVE_AFTER_MS
  ) {
    return publicLogin(login);
  }
  const host = new URL(login.server_url).hostname;
  if (host === "denied.example.org") {
    login.state = "denied";
  } else {
    const credentialId = `cred_studio_${String(sequence)}`;
    login.state = "approved";
    login.credential_id = credentialId;
    servers = [
      ...servers.filter((s) => s.host !== host),
      {
        credential_id: credentialId,
        server_url: login.server_url,
        host,
        account_name: "Анна Петрова",
        scopes: ["git:read", "git:write"],
        expires_at: "2027-01-30T09:00:00Z",
        state: "ok",
      },
    ];
  }
  return publicLogin(login);
};

export const gitServerDemoRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/git/servers",
    handler: () => demoJson({ items: servers }),
  },
  {
    method: "POST",
    pattern: "/git/servers/login",
    handler: (req) => {
      const body = (req.body ?? {}) as Record<string, unknown>;
      const raw = typeof body.server_url === "string" ? body.server_url : "";
      const host = hostOf(raw);
      if (host === null) {
        return demoError(422, "git_server_url_invalid", "Bad address");
      }
      if (host === "other.example.org") {
        return demoError(422, "git_server_not_studio", "Not a Studio");
      }
      if (host === "down.example.org") {
        return demoError(502, "git_server_unreachable", "Unreachable");
      }
      sequence += 1;
      const base = `https://${host}`;
      const login: DemoLogin = {
        login_id: `gsl_demo_${String(sequence)}`,
        server_url: base,
        state: "pending",
        user_code: "BCDF-2345",
        verification_uri_complete: `${base}/device?code=BCDF-2345`,
        expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
        credential_id: null,
        code: null,
        startedAt: Date.now(),
      };
      logins.set(login.login_id, login);
      return demoJson(advance(login));
    },
  },
  {
    method: "GET",
    pattern: "/git/servers/login/:loginId",
    handler: (req) => {
      const login = logins.get(String(req.params.loginId));
      return login ? demoJson(advance(login)) : demoError(404, "not_found", "");
    },
  },
  {
    method: "DELETE",
    pattern: "/git/servers/login/:loginId",
    handler: (req) => {
      logins.delete(String(req.params.loginId));
      return demoNoContent();
    },
  },
  {
    method: "GET",
    pattern: "/git/servers/:credentialId/projects",
    handler: (req) => {
      const server = servers.find(
        (s) => s.credential_id === req.params.credentialId,
      );
      if (!server) return demoError(404, "not_found", "");
      if (server.state !== "ok") {
        return demoError(401, "auth_failed", "Access revoked");
      }
      const q = (queryString(req, "q") ?? "").toLowerCase();
      const items = PROJECTS.items.filter((p) =>
        p.name.toLowerCase().includes(q),
      );
      return demoJson({ ...PROJECTS, items, total: items.length });
    },
  },
  {
    method: "DELETE",
    pattern: "/git/servers/:credentialId",
    handler: (req) => {
      servers = servers.filter(
        (s) => s.credential_id !== req.params.credentialId,
      );
      return demoNoContent();
    },
  },
];
