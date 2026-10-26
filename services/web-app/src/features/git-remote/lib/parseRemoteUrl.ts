import type { GitProvider } from "@entities/git-remote";

// Разбор адреса репозитория на клиенте. Правила те же, что у сервера: общие
// векторы лежат в contracts/git-sync/url_cases.json, и оба разбора проходят их
// одним тестом. Здесь разбор нужен, чтобы сразу показать, что за адрес введён,
// убрать токен из строки и подсказать, где его выпускать. Решает всё равно сервер.

export type RemoteUrlKind = "https" | "http" | "ssh" | "file";

export type RemoteUrlPolicy = {
  /** Открытый http: по умолчанию запрещён. */
  allow_http?: boolean;
  /** Папка на этом компьютере: по умолчанию запрещена. */
  allow_local?: boolean;
};

export type ParsedRemoteUrl = {
  /** Каноничный адрес без пароля и токена. */
  display_url: string;
  kind: RemoteUrlKind;
  host: string | null;
  /** Порт из адреса; для ssh это порт ssh, а не сайта. */
  port: number | null;
  /** Пользователь ssh (по умолчанию git); у остальных null. */
  user: string | null;
  provider: GitProvider;
  owner: string | null;
  repo: string | null;
  /** Путь внутри сервера, как он написан в адресе (без начального слэша). */
  path: string;
  /** В адресе был токен или пароль: он отброшен и нигде не сохраняется. */
  token_stripped: boolean;
};

export type RemoteUrlErrorCode = "url_invalid" | "url_scheme_forbidden";

export type ParseRemoteUrlResult =
  { ok: true; url: ParsedRemoteUrl } | { ok: false; error: RemoteUrlErrorCode };

const MAX_LENGTH = 2048;

const INVALID: ParseRemoteUrlResult = { ok: false, error: "url_invalid" };
const FORBIDDEN: ParseRemoteUrlResult = {
  ok: false,
  error: "url_scheme_forbidden",
};

// Пробелы и управляющие символы любого вида, в том числе перевод строки и NUL.
// eslint-disable-next-line no-control-regex
const CONTROL_OR_SPACE = /[\s\u0000-\u001f\u007f]/u;
// Процентное кодирование управляющих символов: %00..%1f и %7f.
const ENCODED_CONTROL = /%(?:[01][0-9a-f]|7f)/i;
// Символы оболочки, запросы, якоря и скобки: в адресе репозитория им не место.
const FORBIDDEN_CHARS = /[;|&$`<>"'\\(){}[\]*?!^#]/;
const PATH_CHARS = /^[\p{L}\p{N}._~\-/%+=,@:]*$/u;
const SCHEME = /^([a-z][a-z0-9+.-]*):\/\/(.*)$/is;
const TRANSPORT_HELPER = /^[a-z][a-z0-9+.-]*::/i;
const SCP_LIKE = /^(?:([^@/:]+)@)?([^:/@]+):(?!\/\/)(.*)$/;
const HOST_LABEL = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;
const SSH_USER = /^[A-Za-z0-9_][A-Za-z0-9._-]*$/;

const providerOf = (host: string | null): GitProvider => {
  if (!host) return "other";
  if (host === "github.com") return "github";
  if (host === "gitlab.com" || host.startsWith("gitlab.")) return "gitlab";
  if (host === "codeberg.org" || host.startsWith("gitea.")) return "gitea";
  if (host === "bitbucket.org") return "bitbucket";
  return "other";
};

const validHost = (host: string): boolean => {
  if (host === "") return false;
  return host.split(".").every((label) => HOST_LABEL.test(label));
};

const parsePort = (raw: string | undefined): number | null | undefined => {
  if (raw === undefined) return null;
  if (!/^\d{1,5}$/.test(raw)) return undefined;
  const port = Number(raw);
  return port >= 1 && port <= 65535 ? port : undefined;
};

type PathParts = { segments: string[]; clean: string };

// Путь после хоста: без запроса, якоря, «..» и с хотя бы одним сегментом.
const readPath = (path: string): PathParts | null => {
  if (!PATH_CHARS.test(path)) return null;
  const segments = path.split("/").filter((segment) => segment !== "");
  if (segments.length === 0) return null;
  if (segments.some((segment) => segment === "." || segment === ".."))
    return null;
  return { segments, clean: path.replace(/\/$/, "") };
};

const ownerAndRepo = (
  segments: string[],
): { owner: string | null; repo: string | null } => {
  const rest = [...segments];
  const last = rest.pop();
  return {
    owner: rest.length > 0 ? rest.join("/") : null,
    repo: last ? last.replace(/\.git$/i, "") || last : null,
  };
};

type Draft = {
  kind: RemoteUrlKind;
  host: string | null;
  port: number | null;
  user: string | null;
  path: PathParts;
  token_stripped: boolean;
};

const finish = (
  draft: Draft,
  policy: RemoteUrlPolicy,
): ParseRemoteUrlResult => {
  if (draft.kind === "http" && !policy.allow_http) return FORBIDDEN;
  if (draft.kind === "file" && !policy.allow_local) return FORBIDDEN;
  const { owner, repo } = ownerAndRepo(draft.path.segments);
  const authority =
    draft.kind === "file"
      ? ""
      : `${draft.kind === "ssh" ? `${draft.user ?? "git"}@` : ""}${draft.host ?? ""}${draft.port === null ? "" : `:${String(draft.port)}`}`;
  return {
    ok: true,
    url: {
      display_url: `${draft.kind}://${authority}${draft.path.clean.startsWith("/") ? "" : "/"}${draft.path.clean}`,
      kind: draft.kind,
      host: draft.host,
      port: draft.port,
      user: draft.kind === "ssh" ? (draft.user ?? "git") : null,
      provider: draft.kind === "file" ? "other" : providerOf(draft.host),
      owner: draft.kind === "file" ? null : owner,
      repo,
      path: draft.path.clean.replace(/^\/+/, ""),
      token_stripped: draft.token_stripped,
    },
  };
};

const parseSchemeUrl = (
  scheme: string,
  rest: string,
  policy: RemoteUrlPolicy,
): ParseRemoteUrlResult => {
  const kindOf: Record<string, RemoteUrlKind | undefined> = {
    https: "https",
    http: "http",
    ssh: "ssh",
    file: "file",
  };
  const kind = kindOf[scheme];
  if (!kind) return FORBIDDEN;

  const slash = rest.indexOf("/");
  const authority = slash === -1 ? rest : rest.slice(0, slash);
  const pathPart = slash === -1 ? "" : rest.slice(slash);

  if (kind === "file") {
    if (authority !== "") return INVALID;
    const path = readPath(pathPart);
    if (!path) return INVALID;
    return finish(
      { kind, host: null, port: null, user: null, path, token_stripped: false },
      policy,
    );
  }

  const at = authority.lastIndexOf("@");
  const userinfo = at === -1 ? null : authority.slice(0, at);
  const hostPort = at === -1 ? authority : authority.slice(at + 1);
  const colon = hostPort.lastIndexOf(":");
  const host = (
    colon === -1 ? hostPort : hostPort.slice(0, colon)
  ).toLowerCase();
  const port = parsePort(colon === -1 ? undefined : hostPort.slice(colon + 1));
  if (!validHost(host) || port === undefined) return INVALID;
  const path = readPath(pathPart);
  if (!path) return INVALID;

  if (kind === "ssh") {
    // Пароль в ssh-адресе недопустим, имя не может начинаться с дефиса.
    if (
      userinfo !== null &&
      (userinfo.includes(":") || !SSH_USER.test(userinfo))
    )
      return INVALID;
    return finish(
      {
        kind,
        host,
        port,
        user: userinfo && userinfo !== "" ? userinfo : "git",
        path,
        token_stripped: false,
      },
      policy,
    );
  }
  return finish(
    {
      kind,
      host,
      port,
      user: null,
      path,
      token_stripped: userinfo !== null && userinfo !== "",
    },
    policy,
  );
};

const parseScpLike = (
  user: string | undefined,
  host: string,
  path: string,
  policy: RemoteUrlPolicy,
): ParseRemoteUrlResult => {
  const lowered = host.toLowerCase();
  // Одна буква перед двоеточием: скорее диск Windows, чем сервер.
  if (lowered.length < 2 || !validHost(lowered)) return INVALID;
  if (user !== undefined && !SSH_USER.test(user)) return INVALID;
  const parsedPath = readPath(path);
  if (!parsedPath) return INVALID;
  return finish(
    {
      kind: "ssh",
      host: lowered,
      port: null,
      user: user ?? "git",
      path: parsedPath,
      token_stripped: false,
    },
    policy,
  );
};

export const parseRemoteUrl = (
  input: string,
  policy: RemoteUrlPolicy = {},
): ParseRemoteUrlResult => {
  const value = input.trim();
  if (value === "" || value.length > MAX_LENGTH) return INVALID;
  if (CONTROL_OR_SPACE.test(value) || ENCODED_CONTROL.test(value))
    return INVALID;
  if (value.startsWith("-") || FORBIDDEN_CHARS.test(value)) return INVALID;

  if (TRANSPORT_HELPER.test(value)) return FORBIDDEN;

  const scheme = SCHEME.exec(value);
  if (scheme) {
    return parseSchemeUrl(
      (scheme[1] ?? "").toLowerCase(),
      scheme[2] ?? "",
      policy,
    );
  }

  if (value.startsWith("/")) {
    const path = readPath(value);
    if (!path) return INVALID;
    return finish(
      {
        kind: "file",
        host: null,
        port: null,
        user: null,
        path,
        token_stripped: false,
      },
      policy,
    );
  }

  const scp = SCP_LIKE.exec(value);
  if (scp?.[2] !== undefined) {
    return parseScpLike(scp[1], scp[2], scp[3] ?? "", policy);
  }
  return INVALID;
};

// --- переписывание адреса ----------------------------------------------------------

/** Адрес для ssh в привычном виде git@host:owner/repo.git (с портом остаётся ssh://). */
export const toSshUrl = (url: ParsedRemoteUrl): string | null => {
  if (!url.host || url.kind === "file") return null;
  if (url.kind === "ssh") return url.display_url;
  return `ssh://git@${url.host}/${url.path}`;
};

/** Короткая запись scp: удобнее читать и копировать, чем ssh://. */
export const toScpLikeUrl = (url: ParsedRemoteUrl): string | null => {
  if (!url.host || url.kind === "file") return null;
  if (url.kind === "ssh" && url.port !== null) return url.display_url;
  return `${url.user ?? "git"}@${url.host}:${url.path}`;
};

/** Тот же репозиторий по https: порт ssh к сайту не относится. */
export const toHttpsUrl = (url: ParsedRemoteUrl): string | null => {
  if (!url.host || url.kind === "file") return null;
  if (url.kind === "https") return url.display_url;
  return `https://${url.host}/${url.path}`;
};
