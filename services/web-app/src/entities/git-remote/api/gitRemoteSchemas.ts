import { z } from "zod";

import {
  GitHostKeySchema,
  GitProviderInfoSchema,
  GitTlsCertificateSchema,
} from "@entities/git-sync";

// Доступы к репозиториям, ключи серверов, проверка адреса, клонирование.
// Секреты (токены) только входят в запросы и никогда не возвращаются.

export const GIT_CREDENTIAL_KINDS = ["pat", "ssh_key"] as const;
export type GitCredentialKind = (typeof GIT_CREDENTIAL_KINDS)[number];

export const GIT_CREDENTIAL_STATUSES = [
  "unverified",
  "ok",
  "auth_failed",
  "unreadable",
] as const;
export type GitCredentialStatus = (typeof GIT_CREDENTIAL_STATUSES)[number];

export const GIT_PROVIDERS = [
  "github",
  "gitlab",
  "gitea",
  "bitbucket",
  "other",
] as const;
export type GitProvider = (typeof GIT_PROVIDERS)[number];

export const GIT_TOKEN_SUFFICIENCY = [
  "sufficient",
  "too_narrow",
  "too_broad",
  "unknown",
] as const;
export type GitTokenSufficiency = (typeof GIT_TOKEN_SUFFICIENCY)[number];

export const GIT_PROBE_RELATIONS = [
  "empty",
  "studio_project",
  "same_project",
  "same_project_unrelated_history",
  "other_project",
  "not_studio_project",
  "unknown",
] as const;
export type GitProbeRelation = (typeof GIT_PROBE_RELATIONS)[number];

const isOneOf =
  <T extends string>(values: readonly T[]) =>
  (value: unknown): value is T =>
    typeof value === "string" && (values as readonly string[]).includes(value);

export const isGitCredentialKind = isOneOf(GIT_CREDENTIAL_KINDS);
export const isGitCredentialStatus = isOneOf(GIT_CREDENTIAL_STATUSES);
export const isGitProvider = isOneOf(GIT_PROVIDERS);
export const isGitTokenSufficiency = isOneOf(GIT_TOKEN_SUFFICIENCY);
export const isGitProbeRelation = isOneOf(GIT_PROBE_RELATIONS);

// --- доступы --------------------------------------------------------------------

// Что известно о токене после проверки: чей он, какие права, до какого срока.
export const GitTokenInfoSchema = z.object({
  login: z.string().nullish(),
  scopes: z.array(z.string()),
  expires_at: z.string().nullish(),
  sufficiency: z.string(), // sufficient | too_narrow | too_broad | unknown
  missing: z.array(z.string()), // каких прав не хватает для чтения и записи
});

export const GitCredentialSchema = z.object({
  id: z.string(),
  kind: z.string(),
  label: z.string(),
  host: z.string(),
  username: z.string().nullish(),
  status: z.string(),
  token_family: z.string().nullish(), // только префикс, например github_pat
  public_key: z.string().nullish(),
  fingerprint_sha256: z.string().nullish(),
  created_at: z.string(),
  last_used_at: z.string().nullish(),
  expires_at: z.string().nullish(), // срок токена, если известен
  used_by: z.array(z.object({ project_id: z.string(), name: z.string() })),
});

export const GitCredentialListSchema = z.array(GitCredentialSchema);

// Итог «Проверить» у сохранённого токена; отказ сервера приходит ошибкой с кодом, а не этим ответом.
export const GitCredentialCheckSchema = z.object({
  credential: GitCredentialSchema, // с обновлёнными сроком и статусом
  provider_info: GitProviderInfoSchema,
  token_info: GitTokenInfoSchema.nullish(), // null: у этого провайдера токен проверить нельзя
});

export const CreateCredentialRequestSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("pat"),
    label: z.string(),
    host: z.string(),
    username: z.string().nullish(),
    token: z.string(),
  }),
  z.object({
    kind: z.literal("ssh_key"),
    label: z.string(),
    host: z.string(),
    port: z.number().nullish(),
  }),
]);

// Пустой или отсутствующий token оставляет сохранённый.
export const UpdateCredentialRequestSchema = z.object({
  label: z.string().nullish(),
  username: z.string().nullish(),
  token: z.string().nullish(),
});

// --- ключи серверов -------------------------------------------------------------

export const GitHostSchema = z.object({
  host: z.string(),
  port: z.number().nullish(),
  key_types: z.array(z.string()),
  fingerprints_sha256: z.array(z.string()),
  added_at: z.string(),
});

export const GitHostListSchema = z.array(GitHostSchema);

// Отпечаток-заглушка: запрос на доверие без `replace` с ней не меняет ключ, а
// заставляет сервер ответить 409 host_key_changed с тем ключом, который он
// предъявляет сейчас. Так узнаём новый отпечаток, когда проверка его не принесла.
export const REVEAL_FINGERPRINT = "SHA256:reveal";

export const TrustHostRequestSchema = z.object({
  host: z.string(),
  port: z.number().nullish(),
  fingerprint_sha256: z.string(),
  replace: z.boolean().nullish(),
  confirm_host: z.string().nullish(),
});

// Настройки сервера, общие для всех проектов: подмена провайдера, свой CA, закреплённый сертификат.
export const GitHostSettingsSchema = z.object({
  host: z.string(),
  port: z.number().nullish(),
  provider_override: z.string().nullish(),
  provider_info: GitProviderInfoSchema,
  ca_present: z.boolean(),
  pinned_fingerprint: z.string().nullish(),
});

export const GitHostSettingsListSchema = z.array(GitHostSettingsSchema);

// Отсутствующее поле оставляет значение, null сбрасывает его; ca_pem принимает только PEM сертификата.
export const UpdateGitHostSettingsRequestSchema = z.object({
  host: z.string(),
  port: z.number().nullish(),
  provider_override: z.string().nullish(),
  ca_pem: z.string().nullish(),
  pinned_fingerprint: z.string().nullish(),
});

// --- секреты и общие папки ------------------------------------------------------

export const SecretsStatusSchema = z.object({
  ok: z.boolean(),
  source: z.string(), // file | env
  permissions_enforced: z.boolean(),
  credentials_total: z.number(),
  credentials_unreadable: z.number(),
  data_dir_shared_folder: z
    .object({ provider: z.string(), root: z.string() })
    .nullish(),
});

export const SharedFolderSchema = z.object({
  detected: z.boolean(),
  provider: z.string().nullish(),
  root: z.string().nullish(),
  evidence: z.array(z.string()),
});

// --- проверка адреса ------------------------------------------------------------

export const ProbeRequestSchema = z.object({
  url: z.string(),
  credential_id: z.string().nullish(),
  project_id: z.string().nullish(),
  branch: z.string().nullish(),
  insecure_http: z.boolean().nullish(),
});

export const ProbeUrlSchema = z.object({
  display_url: z.string(), // без userinfo
  kind: z.string(), // https | ssh | file | http
  host: z.string().nullish(),
  provider: z.string(),
  owner: z.string().nullish(),
  repo: z.string().nullish(),
  token_stripped: z.boolean(),
});

export const ProbeProjectSchema = z.object({
  id: z.string(),
  name: z.string(),
  pack_id: z.string(),
  template_id: z.string(),
  template_version: z.string(),
  kind: z.string(),
  staffing: z.string(),
  authors_count: z.number(),
});

export const ProbeSchema = z.object({
  ok: z.boolean(),
  error: z
    .object({
      code: z.string(),
      detail: z.string(),
      host_keys: z.array(GitHostKeySchema).nullish(),
      certificate: GitTlsCertificateSchema.nullish(), // tls_untrusted_ca
      expected: z.string().nullish(), // tls_pin_mismatch: закреплённый отпечаток
      actual: z.string().nullish(), // tls_pin_mismatch: отпечаток, который сервер предъявил сейчас
    })
    .nullish(),
  url: ProbeUrlSchema,
  provider_info: GitProviderInfoSchema.nullish(), // url.provider совпадает с provider_info.id
  token_info: GitTokenInfoSchema.nullish(), // только для проверки с токеном
  reachable: z.boolean(),
  auth_ok: z.boolean(),
  empty: z.boolean(),
  default_branch: z.string().nullish(),
  branches: z.array(z.string()),
  relation: z.string(),
  project: ProbeProjectSchema.nullish(),
  schema_access: z.string().nullish(), // full | read_only | files_only
  required_studio: z.string().nullish(),
  template_available: z.boolean().nullish(),
});

// --- клонирование ---------------------------------------------------------------

export const CloneRequestSchema = z.object({
  url: z.string(),
  credential_id: z.string().nullish(),
  branch: z.string().nullish(),
  folder: z.string(),
  name: z.string().nullish(),
  insecure_http: z.boolean().nullish(),
});

export const CloneDefaultsSchema = z.object({
  folder: z.string(),
});

export type GitCredential = z.infer<typeof GitCredentialSchema>;
export type GitCredentialCheck = z.infer<typeof GitCredentialCheckSchema>;
export type CreateCredentialRequest = z.infer<
  typeof CreateCredentialRequestSchema
>;
export type UpdateCredentialRequest = z.infer<
  typeof UpdateCredentialRequestSchema
>;
export type GitHost = z.infer<typeof GitHostSchema>;
export type GitHostSettings = z.infer<typeof GitHostSettingsSchema>;
export type UpdateGitHostSettingsRequest = z.infer<
  typeof UpdateGitHostSettingsRequestSchema
>;
export type GitTokenInfo = z.infer<typeof GitTokenInfoSchema>;
export type TrustHostRequest = z.infer<typeof TrustHostRequestSchema>;
export type SecretsStatus = z.infer<typeof SecretsStatusSchema>;
export type SharedFolder = z.infer<typeof SharedFolderSchema>;
export type ProbeRequest = z.infer<typeof ProbeRequestSchema>;
export type ProbeUrl = z.infer<typeof ProbeUrlSchema>;
export type ProbeProject = z.infer<typeof ProbeProjectSchema>;
export type Probe = z.infer<typeof ProbeSchema>;
export type CloneRequest = z.infer<typeof CloneRequestSchema>;
export type CloneDefaults = z.infer<typeof CloneDefaultsSchema>;
