import { z } from "zod";

import { GIT_PROVIDERS, type GitProvider } from "../api/gitRemoteSchemas";
import catalogJson from "./providers.json";

// Каталог git-провайдеров: определение по хосту, адреса API, права токена.
// Данные лежат в providers.json рядом: файл совпадает побайтно с
// contracts/git-sync/providers.json (так же, как копия на бэкенде), векторы
// provider_cases.json общие с core/git_sync/providers.py.

const LinkTemplateSchema = z.object({
  kind: z.enum(["prefilled", "plain"]),
  broad: z.boolean(),
  path: z.string(),
  query: z.array(z.object({ key: z.string(), value: z.string() })),
});

const SshLinkTemplateSchema = z.object({
  kind: z.enum(["prefilled", "plain"]),
  path: z.string(),
});

const ProviderSpecSchema = z.object({
  id: z.enum(GIT_PROVIDERS),
  label: z.string(),
  host_rules: z.array(
    z.object({
      match: z.enum(["exact", "first_label", "label"]),
      value: z.string(),
    }),
  ),
  api: z.object({
    base: z.string().nullable(),
    base_by_host: z.record(z.string(), z.string()),
    detect: z
      .object({
        path: z.string(),
        version_header: z.string().nullable(),
        version_key: z.string().nullable(),
      })
      .nullable(),
  }),
  auth_variants: z.array(z.enum(["token", "ssh_user_key", "deploy_key"])),
  limits: z.object({ name: z.number(), description: z.number() }),
  token_links: z
    .object({
      primary: LinkTemplateSchema,
      fallback: LinkTemplateSchema.nullable(),
    })
    .nullable(),
  permissions: z.object({
    required: z.array(z.string()),
    optional: z.array(z.string()),
    too_broad: z.array(z.string()),
    implies: z.record(z.string(), z.array(z.string())),
    human: z.object({ ru: z.string(), en: z.string() }),
  }),
  introspection: z
    .object({
      method: z.string(),
      path: z.string(),
      auth: z.string(),
      scopes: z.string(),
    })
    .nullable(),
  ssh_links: z
    .object({
      user_keys: SshLinkTemplateSchema,
      deploy_key: SshLinkTemplateSchema,
    })
    .nullable(),
  docs_url: z.string().nullable(),
});

const CatalogSchema = z.object({
  version: z.number(),
  detected_by: z.array(z.string()),
  auth_variants: z.array(z.string()),
  defaults: z.object({
    token_name: z.object({
      with_project: z.string(),
      without_project: z.string(),
    }),
    token_description: z.record(z.string(), z.string()),
    expires_in_days: z.number(),
    instance_prefix_max_depth: z.number(),
  }),
  providers: z.array(ProviderSpecSchema),
});

export type ProviderSpec = z.infer<typeof ProviderSpecSchema>;
export type ProviderCatalog = z.infer<typeof CatalogSchema>;
export type ProviderAuthVariant = ProviderSpec["auth_variants"][number];
export type TokenSufficiency =
  "sufficient" | "too_narrow" | "too_broad" | "unknown";

export const PROVIDER_CATALOG: ProviderCatalog =
  CatalogSchema.parse(catalogJson);

export const providerSpec = (provider: GitProvider): ProviderSpec => {
  const spec = PROVIDER_CATALOG.providers.find((item) => item.id === provider);
  if (!spec) throw new Error(`нет провайдера ${provider} в каталоге`);
  return spec;
};

// --- определение провайдера ---------------------------------------------------

const ruleMatches = (
  rule: ProviderSpec["host_rules"][number],
  host: string,
): boolean => {
  const labels = host.split(".");
  if (rule.match === "exact") return host === rule.value;
  if (rule.match === "first_label") return labels[0] === rule.value;
  return labels.includes(rule.value);
};

/** Провайдер по имени хоста; первое совпадение в порядке каталога, иначе other. */
export const providerForHost = (host: string | null): GitProvider => {
  if (!host) return "other";
  const name = host.toLowerCase();
  const spec = PROVIDER_CATALOG.providers.find((item) =>
    item.host_rules.some((rule) => ruleMatches(rule, name)),
  );
  return spec ? spec.id : "other";
};

export type ProviderDetection = {
  id: GitProvider;
  detected_by: "override" | "host" | "api" | "unknown";
  version: string | null;
};

export type DetectProviderOptions = {
  /** Выбор человека по хостам (ключ в нижнем регистре). */
  overrides?: Readonly<Record<string, GitProvider>>;
  /** Ответ API сервера на проверку. */
  api?: { provider: GitProvider; version: string | null } | null;
};

/**
 * Порядок такой: выбор человека для хоста, имя хоста, ответ API, иначе other и unknown.
 * Версия берётся из ответа API, если он назвал того же провайдера, что выбран.
 */
export const detectProvider = (
  host: string | null,
  options: DetectProviderOptions = {},
): ProviderDetection => {
  const name = host ? host.toLowerCase() : null;
  const { overrides, api } = options;
  const override = name && overrides ? overrides[name] : undefined;
  const heuristic = providerForHost(name);
  let id: GitProvider;
  let detectedBy: ProviderDetection["detected_by"];
  if (override) {
    id = override;
    detectedBy = "override";
  } else if (heuristic !== "other") {
    id = heuristic;
    detectedBy = "host";
  } else if (api) {
    id = api.provider;
    detectedBy = "api";
  } else {
    id = "other";
    detectedBy = "unknown";
  }
  return {
    id,
    detected_by: detectedBy,
    version: api?.provider === id ? api.version : null,
  };
};

// --- адреса сайта и API -------------------------------------------------------

const SUBPATH_SEGMENT = /^[A-Za-z0-9._~%-]+$/;

export type WebBaseInput = {
  host: string | null;
  port: number | null;
  secure?: boolean;
  subpath?: string;
};

/**
 * Корень сайта сервера: схема, хост, порт и путь установки (https://host/gitlab).
 * Порт нужен только у https/http; порт ssh к сайту не относится, его передают как null.
 * Недопустимый путь установки даёт null.
 */
export const webBase = ({
  host,
  port,
  secure = true,
  subpath = "",
}: WebBaseInput): string | null => {
  if (!host) return null;
  const trimmed = subpath.replace(/^\/+|\/+$/g, "");
  const segments = trimmed ? trimmed.split("/") : [];
  const valid = segments.every(
    (segment) =>
      SUBPATH_SEGMENT.test(segment) && segment !== "." && segment !== "..",
  );
  if (!valid) return null;
  const authority = host + (port ? `:${String(port)}` : "");
  return `${secure ? "https" : "http"}://${authority}${segments
    .map((segment) => `/${segment}`)
    .join("")}`;
};

/** Корень API: известный хост (api.github.com) или шаблон от корня сайта. */
export const apiBase = (
  provider: GitProvider,
  host: string | null,
  base: string | null,
): string | null => {
  const { api } = providerSpec(provider);
  const known = host ? api.base_by_host[host.toLowerCase()] : undefined;
  if (known) return known;
  if (api.base === null || base === null) return null;
  return api.base.replace("{web_base}", base);
};

/**
 * Возможные пути установки по пути репозитория: у сервера под /gitlab группа и
 * проект идут после префикса. От короткого к длинному; после префикса остаются
 * как минимум владелец и репозиторий.
 */
export const instancePrefixCandidates = (
  segments: readonly string[],
): string[] => {
  const longest = Math.min(
    segments.length - 2,
    PROVIDER_CATALOG.defaults.instance_prefix_max_depth - 1,
  );
  const result: string[] = [];
  for (let depth = 0; depth <= longest; depth += 1) {
    result.push(
      segments
        .slice(0, depth)
        .map((segment) => `/${segment}`)
        .join(""),
    );
  }
  return result;
};

// --- права токена -------------------------------------------------------------

export type ScopeAssessment = {
  sufficiency: TokenSufficiency;
  missing: string[];
};

/**
 * Хватает ли найденных прав для чтения и записи. null значит, что права
 * прочитать нельзя (старый сервер, точный токен): вывод unknown, дальше работает
 * проверка git. Нехватка прав (push не пройдёт) важнее, чем лишние права.
 */
export const assessScopes = (
  provider: GitProvider,
  scopes: readonly string[] | null,
): ScopeAssessment => {
  if (scopes === null) return { sufficiency: "unknown", missing: [] };
  const { permissions } = providerSpec(provider);
  const granted = new Set(scopes);
  for (const scope of scopes) {
    for (const implied of permissions.implies[scope] ?? [])
      granted.add(implied);
  }
  const missing = permissions.required.filter((scope) => !granted.has(scope));
  if (missing.length > 0) return { sufficiency: "too_narrow", missing };
  if (scopes.some((scope) => permissions.too_broad.includes(scope))) {
    return { sufficiency: "too_broad", missing: [] };
  }
  return { sufficiency: "sufficient", missing: [] };
};
