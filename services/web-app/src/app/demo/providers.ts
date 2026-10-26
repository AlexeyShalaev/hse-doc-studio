import {
  assessScopes,
  detectProvider,
  findHostSettings,
  isGitProvider,
  providerSpec,
  type GitCredential,
  type GitCredentialCheck,
  type GitHostSettings,
  type GitProvider,
  type GitTokenInfo,
  type ProviderDetection,
} from "@entities/git-remote";
import type { GitTlsCertificate } from "@entities/git-sync";
import { DAY, isoAgo, isoAt, nowMs } from "./clock";

// Серверы, токены и сертификаты демо. Настоящие ответы дают бэкенд и сам сервер;
// здесь по имени хоста и по слову в токене получается каждое состояние, которое
// интерфейс умеет показывать. Подсказки по словам показывает выбор сценария.

/** Какой ответ даст проверка токена. */
export type DemoTokenMode =
  "sufficient" | "narrow" | "broad" | "expired" | "opaque" | "revoked";

type World = {
  hostSettings: GitHostSettings[];
  tokenModes: Record<string, DemoTokenMode>;
  forcedTokenMode: DemoTokenMode | null;
  serverVersions: Record<string, string>;
};

const WORDS: [string, DemoTokenMode][] = [
  ["narrow", "narrow"],
  ["broad", "broad"],
  ["expired", "expired"],
  ["opaque", "opaque"],
  ["revoked", "revoked"],
];

/** Режим токена: слово в самом токене, затем сценарий, затем вид токена. */
export const tokenModeOf = (token: string, world: World): DemoTokenMode => {
  const lower = token.toLowerCase();
  const word = WORDS.find(([key]) => lower.includes(key));
  if (word) return word[1];
  if (world.forcedTokenMode) return world.forcedTokenMode;
  // Точный токен GitHub прав не показывает: проверить их нельзя.
  if (lower.startsWith("github_pat_")) return "opaque";
  return "sufficient";
};

/** Когда токен перестанет действовать: у каждого режима свой срок. */
export const expiryFor = (mode: DemoTokenMode): string | null => {
  switch (mode) {
    case "sufficient":
      return isoAt(nowMs() + 90 * DAY);
    case "narrow":
      return isoAt(nowMs() + 20 * DAY);
    case "expired":
      return isoAgo(3 * DAY);
    default:
      return null;
  }
};

// --- тип сервера ------------------------------------------------------------------

export const DEFAULT_VERSION = "17.3.1";

/** Тип сервера: выбор человека, имя хоста, ответ API (хосты forge.*), иначе other. */
export const detectDemoProvider = (
  world: World,
  host: string | null,
  port: number | null,
): ProviderDetection => {
  const name = host?.toLowerCase() ?? null;
  const version = name ? (world.serverVersions[name] ?? null) : null;
  const saved = findHostSettings(world.hostSettings, name, port);
  const override = saved?.provider_override;
  if (override && isGitProvider(override)) {
    return {
      id: override,
      detected_by: "override",
      version: override === "gitlab" ? version : null,
    };
  }
  const local = detectProvider(name);
  if (local.detected_by === "host") {
    return { ...local, version: local.id === "gitlab" ? version : null };
  }
  if (name?.startsWith("forge.")) {
    return {
      id: "gitlab",
      detected_by: "api",
      version: version ?? "16.11.2",
    };
  }
  return local;
};

// --- сертификаты ------------------------------------------------------------------

const certificateFor = (host: string): GitTlsCertificate => {
  const selfSigned = host.split(".").includes("lab");
  return {
    fingerprint_sha256: selfSigned
      ? "SHA256:s3lfS1gnedDemoCertificateFingerprint0123456789abcd"
      : "SHA256:b1Kq0vU7m4Zl9Xc2Tn8RjHf3eWyAo5DsPi6GgLxEu0w",
    subject: `CN=${host}`,
    issuer: selfSigned ? `CN=${host}` : "CN=HSE Internal CA",
    not_before: isoAgo(290 * DAY),
    not_after: isoAt(nowMs() + 75 * DAY),
    self_signed: selfSigned,
  };
};

export type DemoTlsIssue = {
  code: "tls_untrusted_ca" | "tls_pin_mismatch";
  detail: string;
  certificate: GitTlsCertificate;
};

/** Серверы внутри сети (*.local) подписаны своим центром, пока человек не доверил его. */
export const tlsIssueFor = (
  world: World,
  host: string | null,
  port: number | null,
): DemoTlsIssue | null => {
  if (!host?.toLowerCase().endsWith(".local")) return null;
  const certificate = certificateFor(host.toLowerCase());
  const saved = findHostSettings(world.hostSettings, host, port);
  if (saved?.pinned_fingerprint) {
    return saved.pinned_fingerprint === certificate.fingerprint_sha256
      ? null
      : {
          code: "tls_pin_mismatch",
          detail: "Сертификат сервера не совпадает с закреплённым.",
          certificate,
        };
  }
  if (saved?.ca_present) return null;
  return {
    code: "tls_untrusted_ca",
    detail:
      "Сертификат сервера выдан неизвестным центром. Добавь его сертификат или подтверди отпечаток.",
    certificate,
  };
};

// --- токены -----------------------------------------------------------------------

const scopesFor = (
  mode: DemoTokenMode,
  provider: GitProvider,
): string[] | null => {
  if (mode === "opaque") return null;
  if (provider === "gitlab") {
    if (mode === "narrow") return ["read_repository"];
    if (mode === "broad") return ["api"];
    return ["read_repository", "write_repository"];
  }
  if (provider === "github") {
    if (mode === "narrow") return ["read:user"];
    if (mode === "broad") return ["repo", "admin:org"];
    return ["repo"];
  }
  return null;
};

/** Что известно о токене: null там, где у сервера нет способа спросить (Bitbucket, чужие серверы). */
export const tokenInfoFor = (
  credential: GitCredential,
  provider: GitProvider,
  mode: DemoTokenMode,
): GitTokenInfo | null => {
  if (providerSpec(provider).introspection === null) return null;
  if (mode === "revoked") return null;
  if (mode === "expired") {
    return {
      login: null,
      scopes: [],
      expires_at: credential.expires_at ?? isoAgo(3 * DAY),
      sufficiency: "unknown",
      missing: [],
    };
  }
  const scopes = scopesFor(mode, provider);
  const verdict = assessScopes(provider, scopes);
  return {
    login: credential.username ?? "ivan-smirnov",
    scopes: scopes ?? [],
    expires_at: credential.expires_at ?? null,
    sufficiency: verdict.sufficiency,
    missing: verdict.missing,
  };
};

/** Итог проверки сохранённого токена: ответ 200 или ошибка с кодом, как у бэкенда. */
export type DemoCheckOutcome =
  | { ok: true; provider: ProviderDetection; info: GitTokenInfo | null }
  | {
      ok: false;
      status: number;
      code: string;
      detail: string;
      extra: Record<string, unknown>;
    };

/** Что ответит проверка токена: данные о токене или отказ с кодом (токен не принят, истёк, сертификат). */
export const checkCredentialOutcome = (
  world: World,
  credential: GitCredential,
): DemoCheckOutcome => {
  const host = credential.host.toLowerCase();
  const provider = detectDemoProvider(world, host, null);
  const tls = tlsIssueFor(world, host, null);
  if (tls) {
    return {
      ok: false,
      status: 502,
      code: tls.code,
      detail: tls.detail,
      extra:
        tls.code === "tls_untrusted_ca"
          ? { certificate: tls.certificate }
          : {
              expected:
                findHostSettings(world.hostSettings, host, null)
                  ?.pinned_fingerprint ?? "",
              actual: tls.certificate.fingerprint_sha256,
            },
    };
  }
  const mode = world.tokenModes[credential.id] ?? "sufficient";
  if (mode === "revoked") {
    return {
      ok: false,
      status: 502,
      code: "auth_failed",
      detail: "Сервер отклонил токен: он отозван или просрочен.",
      extra: {},
    };
  }
  if (mode === "expired") {
    return {
      ok: false,
      status: 502,
      code: "token_expired",
      detail: "Срок действия токена истёк. Выпусти новый.",
      extra: {},
    };
  }
  return {
    ok: true,
    provider,
    info: tokenInfoFor(credential, provider.id, mode),
  };
};

/** Тело ответа проверки токена (credential уже с обновлённым статусом). */
export const checkCredentialBody = (
  credential: GitCredential,
  outcome: Extract<DemoCheckOutcome, { ok: true }>,
): GitCredentialCheck => ({
  credential,
  provider_info: outcome.provider,
  token_info: outcome.info,
});

/** Запись настроек хоста с пересчитанным определением типа сервера. */
export const hostSettingsView = (
  world: World,
  entry: GitHostSettings,
): GitHostSettings => ({
  ...entry,
  provider_info: detectDemoProvider(world, entry.host, entry.port ?? null),
});

export const emptyHostSettings = (
  host: string,
  port: number | null,
): GitHostSettings => ({
  host,
  port,
  provider_override: null,
  provider_info: { id: "other", detected_by: "unknown", version: null },
  ca_present: false,
  pinned_fingerprint: null,
});
