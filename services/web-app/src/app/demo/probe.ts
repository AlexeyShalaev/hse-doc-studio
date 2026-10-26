import type { ProbeUrl } from "@entities/git-remote";
import { fakeUuid } from "./clock";
import { GITHUB_HOST_KEY, type DemoWorld } from "./world";

// Правила демо-проверки адреса. Настоящий разбор живёт на сервере; здесь ровно
// столько, чтобы по виду адреса получить каждый исход. Подсказки по словам в
// адресе показывает выбор сценария.

export type DemoUrlError = { code: string; detail: string };

const providerOf = (host: string): string => {
  if (host === "github.com") return "github";
  if (host === "gitlab.com" || host.startsWith("gitlab.")) return "gitlab";
  if (host === "codeberg.org" || host.startsWith("gitea.")) return "gitea";
  if (host === "bitbucket.org") return "bitbucket";
  return "other";
};

const splitPath = (
  path: string,
): { owner: string | null; repo: string | null } => {
  const parts = path.split("/").filter((part) => part !== "");
  const last = parts.pop();
  return {
    owner: parts.length > 0 ? parts.join("/") : null,
    repo: last ? last.replace(/\.git$/, "") : null,
  };
};

export const parseDemoUrl = (raw: string): ProbeUrl | DemoUrlError => {
  const value = raw.trim();
  const invalid: DemoUrlError = {
    code: "url_invalid",
    detail: "Адрес репозитория не похож на корректный.",
  };
  if (value === "" || /\s/.test(value)) return invalid;

  // Транспорты вида ext::команда запрещены целиком.
  if (/^[a-z][a-z0-9+.-]*::/i.test(value)) {
    return {
      code: "url_scheme_forbidden",
      detail: "Этот тип адреса не поддерживается.",
    };
  }

  const scp = /^(?:[\w.-]+@)?([\w.-]+\.[a-z]{2,}):(?!\/\/)(.+)$/i.exec(value);
  if (scp?.[1] && scp[2] && !value.includes("://")) {
    const host = scp[1].toLowerCase();
    return {
      display_url: `ssh://git@${host}/${scp[2]}`,
      kind: "ssh",
      host,
      provider: providerOf(host),
      ...splitPath(scp[2]),
      token_stripped: false,
    };
  }

  const match =
    /^([a-z][a-z0-9+.-]*):\/\/(?:([^@/]*)@)?([^/:]*)(?::(\d+))?(\/.*)?$/i.exec(
      value,
    );
  if (match) {
    const scheme = (match[1] ?? "").toLowerCase();
    const userinfo = match[2];
    const host = (match[3] ?? "").toLowerCase();
    const path = match[5] ?? "";
    if (scheme === "file") {
      return {
        display_url: `file://${path}`,
        kind: "file",
        host: null,
        provider: "other",
        ...splitPath(path),
        token_stripped: false,
      };
    }
    if (!["https", "http", "ssh"].includes(scheme)) {
      return {
        code: "url_scheme_forbidden",
        detail: "Этот тип адреса не поддерживается.",
      };
    }
    if (host === "" || !host.includes(".")) return invalid;
    const stripped =
      scheme !== "ssh" && userinfo !== undefined && userinfo !== "";
    const shown = scheme === "ssh" && userinfo ? `${userinfo}@` : "";
    return {
      display_url: `${scheme}://${shown}${host}${match[4] ? `:${match[4]}` : ""}${path.replace(/\/$/, "")}`,
      kind: scheme,
      host,
      provider: providerOf(host),
      ...splitPath(path),
      token_stripped: stripped,
    };
  }
  if (value.startsWith("/") || value.startsWith("~")) {
    return {
      display_url: `file://${value}`,
      kind: "file",
      host: null,
      provider: "other",
      ...splitPath(value),
      token_stripped: false,
    };
  }
  return invalid;
};

export const isUrlError = (
  value: ProbeUrl | DemoUrlError,
): value is DemoUrlError => "code" in value;

const has = (url: string, word: string): boolean =>
  url.toLowerCase().includes(word);

const ISSUES: Record<string, DemoUrlError> = {
  offline: {
    code: "offline",
    detail: "Не удалось связаться с сервером. Проверь интернет и адрес.",
  },
  missing: {
    code: "not_found_or_no_access",
    detail: "Репозиторий не найден или к нему нет доступа.",
  },
  tls: {
    code: "tls_error",
    detail: "Сертификат сервера не прошёл проверку.",
  },
  slow: { code: "timeout", detail: "Сервер не ответил за отведённое время." },
  limit: {
    code: "rate_limited",
    detail: "Слишком много запросов, попробуй позже.",
  },
};

// Ошибка доступа по адресу, если она есть: ok: false в ответе проверки.
export const accessIssue = (
  world: DemoWorld,
  parsed: ProbeUrl,
  credentialId: string | null,
): DemoUrlError | null => {
  for (const [word, issue] of Object.entries(ISSUES)) {
    if (has(parsed.display_url, word)) return issue;
  }
  if (has(parsed.display_url, "auth") && !credentialId) {
    return {
      code: "auth_failed",
      detail: "Сервер отклонил доступ: нужен токен с правом записи.",
    };
  }
  if (
    parsed.kind === "ssh" &&
    parsed.host &&
    !world.hosts.some((host) => host.host === parsed.host)
  ) {
    return {
      code: "host_key_unknown",
      detail: "Сервер ещё не в списке доверенных.",
    };
  }
  return null;
};

export const hostKeysFor = (): {
  type: string;
  fingerprint_sha256: string;
}[] => [GITHUB_HOST_KEY];

export type DemoProbeInput = {
  url: string;
  credentialId: string | null;
  projectId: string | null;
};

const PROJECT_INFO = {
  name: "Курсовая работа",
  pack_id: "hse-cs-sse",
  template_id: "coursework",
  template_version: "1.2.0",
  kind: "coursework",
  staffing: "team",
  authors_count: 2,
};

export const runDemoProbe = (
  world: DemoWorld,
  input: DemoProbeInput,
): { status: number; body: unknown } => {
  const parsed = parseDemoUrl(input.url);
  if (isUrlError(parsed)) {
    return { status: 400, body: parsed };
  }
  const base = {
    url: parsed,
    reachable: true,
    auth_ok: true,
    empty: false,
    default_branch: "main",
    branches: ["main", "develop"],
    relation: "studio_project",
    project: null,
    schema_access: "full",
    required_studio: null,
    template_available: true,
  };
  const issue = accessIssue(world, parsed, input.credentialId);
  if (issue) {
    const unreachable = ["offline", "tls_error", "timeout"].includes(
      issue.code,
    );
    return {
      status: 200,
      body: {
        ...base,
        ok: false,
        error: {
          code: issue.code,
          detail: issue.detail,
          host_keys: issue.code === "host_key_unknown" ? hostKeysFor() : null,
        },
        reachable: !unreachable,
        auth_ok: false,
        default_branch: null,
        branches: [],
        relation: "unknown",
        schema_access: null,
        template_available: null,
      },
    };
  }

  const url = parsed.display_url;
  const projectId = input.projectId;
  const project = {
    id: projectId ?? fakeUuid(900),
    ...PROJECT_INFO,
  };
  let relation = projectId ? "empty" : "studio_project";
  if (has(url, "empty")) relation = "empty";
  else if (has(url, "unrelated"))
    relation = projectId ? "same_project_unrelated_history" : "studio_project";
  else if (has(url, "other"))
    relation = projectId ? "other_project" : "studio_project";
  else if (has(url, "same"))
    relation = projectId ? "same_project" : "studio_project";
  else if (has(url, "plain")) relation = "not_studio_project";
  else if (has(url, "newer")) relation = "studio_project";

  if (relation === "empty") {
    return {
      status: 200,
      body: {
        ...base,
        ok: true,
        error: null,
        empty: true,
        default_branch: null,
        branches: [],
        relation,
        schema_access: null,
        template_available: null,
      },
    };
  }
  if (relation === "not_studio_project") {
    return {
      status: 200,
      body: {
        ...base,
        ok: true,
        error: null,
        relation,
        schema_access: null,
        template_available: null,
      },
    };
  }
  const newer = has(url, "newer");
  return {
    status: 200,
    body: {
      ...base,
      ok: true,
      error: null,
      relation,
      project:
        relation === "other_project"
          ? { ...project, id: fakeUuid(901), name: "Чужой проект" }
          : project,
      schema_access: newer ? "read_only" : "full",
      required_studio: newer ? "0.4.0" : null,
      template_available: !has(url, "notemplate"),
    },
  };
};
