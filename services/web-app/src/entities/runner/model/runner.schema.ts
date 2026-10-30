import { z } from "zod";

// Личные раннеры, сопряжение по коду, политика сборок проекта, место сборки и
// облачные сборки локальной Студии. Зеркало api/schemas/personal_runners.py и
// api/schemas/remote_runner.py; эталоны лежат в contracts/server/fixtures
// (MyRunner, ProjectBuildRunners, CompilePlacement, RemoteRunnerStatus...).
// strictObject повторяет extra=forbid бэкенда: лишнее поле значит расхождение сторон.

const iso = z.string().min(1);

/** Состояние своего раннера, как его считает сервер (runner_status в core/jobs/admin.py). */
export const MY_RUNNER_STATES = [
  "online",
  "stale",
  "offline",
  "paused",
  "revoked",
  "disabled",
] as const;
export const MyRunnerStateSchema = z.enum(MY_RUNNER_STATES);
export type MyRunnerState = z.infer<typeof MyRunnerStateSchema>;

export const RunnerHostKindSchema = z.enum(["cli", "desktop"]);
export type RunnerHostKind = z.infer<typeof RunnerHostKindSchema>;

export const AiEndpointFlavorSchema = z.enum(["openai", "ollama"]);
export type AiEndpointFlavor = z.infer<typeof AiEndpointFlavorSchema>;

/** ИИ-адрес, объявленный раннером: сервер знает только имя и вид, URL остаётся у раннера. */
export const DeclaredAiEndpointSchema = z.strictObject({
  name: z.string(),
  flavor: AiEndpointFlavorSchema,
});
export type DeclaredAiEndpoint = z.infer<typeof DeclaredAiEndpointSchema>;

export const MyRunnerSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  state: MyRunnerStateSchema,
  host_kind: RunnerHostKindSchema,
  tags: z.array(z.string()),
  concurrency: z.number().int(),
  ai_concurrency: z.number().int(),
  version: z.string(),
  created_at: iso,
  last_seen_at: iso.nullable(),
  last_seen_ip: z.string().nullable(),
  paused: z.boolean(),
  revoked: z.boolean(),
  running_jobs: z.number().int(),
  ai_endpoints: z.array(DeclaredAiEndpointSchema),
  features: z.array(z.string()),
});
export type MyRunner = z.infer<typeof MyRunnerSchema>;
export const MyRunnerListSchema = z.array(MyRunnerSchema);

export const MyRunnerTokenSchema = z.strictObject({
  id: z.string(),
  label: z.string(),
  created_at: iso,
  expires_at: iso,
  used: z.boolean(),
  revoked: z.boolean(),
});
export type MyRunnerToken = z.infer<typeof MyRunnerTokenSchema>;
export const MyRunnerTokenListSchema = z.array(MyRunnerTokenSchema);

/** Сроки токена регистрации в часах: 1 ч, сутки, неделя (сервер принимает 1–168). */
export const RUNNER_TOKEN_TTLS = [1, 24, 168] as const;

export const CreateMyRunnerTokenRequestSchema = z.strictObject({
  label: z.string().max(128),
  ttl_hours: z.number().int().min(1).max(168),
});
export type CreateMyRunnerTokenRequest = z.infer<
  typeof CreateMyRunnerTokenRequestSchema
>;

export const MyRunnerTokenCreatedSchema = z.strictObject({
  token: MyRunnerTokenSchema,
  secret: z.string(),
  command: z.string(),
  docker_command: z.string(),
});
export type MyRunnerTokenCreated = z.infer<typeof MyRunnerTokenCreatedSchema>;

export const UpdateMyRunnerRequestSchema = z.strictObject({
  name: z.string().min(1).max(128).nullable(),
  paused: z.boolean().nullable(),
});
export type UpdateMyRunnerRequest = z.infer<typeof UpdateMyRunnerRequestSchema>;

export const MyRunnerRotatedSchema = z.strictObject({
  runner: MyRunnerSchema,
  runner_token: z.string(),
  command: z.string(),
});
export type MyRunnerRotated = z.infer<typeof MyRunnerRotatedSchema>;

export const RunnerPairingStatusSchema = z.enum([
  "pending",
  "approved",
  "denied",
  "expired",
]);
export const RunnerPairingInfoSchema = z.strictObject({
  user_code: z.string(),
  name: z.string(),
  host_kind: RunnerHostKindSchema,
  requested_at: iso,
  expires_at: iso,
  client_ip: z.string().nullable(),
  status: RunnerPairingStatusSchema,
});
export type RunnerPairingInfo = z.infer<typeof RunnerPairingInfoSchema>;

export const RunnerPairingDecisionRequestSchema = z.strictObject({
  decision: z.enum(["approve", "deny"]),
});
export type RunnerPairingDecision = z.infer<
  typeof RunnerPairingDecisionRequestSchema
>["decision"];

/** Состояние раннера владельца, которое видит участник проекта: только имя и состояние. */
export const OwnerRunnerStateSchema = z.enum([
  "online",
  "stale",
  "offline",
  "paused",
  "disabled",
]);
export type OwnerRunnerState = z.infer<typeof OwnerRunnerStateSchema>;

export const BuildRunnersPolicySchema = z.enum(["shared", "owner"]);
export type BuildRunnersPolicy = z.infer<typeof BuildRunnersPolicySchema>;

export const ProjectBuildRunnersSchema = z.strictObject({
  policy: BuildRunnersPolicySchema,
  editable: z.boolean(),
  project_kind: z.enum(["personal", "org"]),
  personal_runners_enabled: z.boolean(),
  /** Куда идут сборки того, кто смотрит: личный раннер сначала или только общие. */
  my_builds: z.enum(["personal_first", "shared"]),
  wait_s: z.number().int().min(0),
  owner_runners: z.array(
    z.strictObject({ name: z.string(), state: OwnerRunnerStateSchema }),
  ),
});
export type ProjectBuildRunners = z.infer<typeof ProjectBuildRunnersSchema>;

export const UpdateProjectBuildRunnersRequestSchema = z.strictObject({
  policy: BuildRunnersPolicySchema,
});

export const PLACEMENT_FALLBACKS = [
  "offline",
  "busy",
  "timeout",
  "lost",
  "disabled",
] as const;
export const CompilePlacementSchema = z.strictObject({
  state: z.enum(["waiting_personal", "personal", "shared"]),
  runner_name: z.string().nullable(),
  /** me: раннер того, кто смотрит; owner: раннер владельца проекта. */
  runner_owner: z.enum(["me", "owner"]).nullable(),
  fallback: z.enum(PLACEMENT_FALLBACKS).nullable(),
  wait_s: z.number().int().min(0).nullable(),
});
export type CompilePlacement = z.infer<typeof CompilePlacementSchema>;
export type PlacementFallback = NonNullable<CompilePlacement["fallback"]>;

// Облачные сборки локальной Студии (только локальный режим).

export const REMOTE_RUNNER_STATES = [
  "off",
  "unpaired",
  "pairing",
  "connecting",
  "online",
  "paused",
  "offline",
  "revoked",
  "disabled",
  "error",
] as const;
export const RemoteRunnerStateSchema = z.enum(REMOTE_RUNNER_STATES);
export type RemoteRunnerState = z.infer<typeof RemoteRunnerStateSchema>;

export const RemoteAiEndpointSchema = z.strictObject({
  name: z.string(),
  provider_id: z.string(),
  flavor: AiEndpointFlavorSchema,
  url: z.string(),
});
export type RemoteAiEndpoint = z.infer<typeof RemoteAiEndpointSchema>;

export const RemoteRunnerStatusSchema = z.strictObject({
  enabled: z.boolean(),
  server_url: z.string().nullable(),
  paired: z.boolean(),
  runner_id: z.string().nullable(),
  runner_name: z.string().nullable(),
  state: RemoteRunnerStateSchema,
  /** Код причины для состояний error и offline (каталог ошибок). */
  detail_code: z.string().nullable(),
  running_jobs: z.number().int(),
  concurrency: z.number().int().min(1).max(4),
  yield_to_local: z.boolean(),
  docker: z.enum(["ok", "missing"]),
  tex_image: z.enum(["ready", "missing"]),
  ai_endpoints: z.array(RemoteAiEndpointSchema),
  pairing: z
    .strictObject({
      user_code: z.string(),
      verification_uri_complete: z.string(),
      expires_at: iso,
    })
    .nullable(),
});
export type RemoteRunnerStatus = z.infer<typeof RemoteRunnerStatusSchema>;

export const UpdateRemoteRunnerRequestSchema = z.strictObject({
  enabled: z.boolean().nullable(),
  server_url: z.string().nullable(),
  name: z.string().nullable(),
  concurrency: z.number().int().min(1).max(4).nullable(),
  yield_to_local: z.boolean().nullable(),
  ai_endpoints: z
    .array(z.strictObject({ name: z.string(), provider_id: z.string() }))
    .nullable(),
});
export type UpdateRemoteRunnerRequest = z.infer<
  typeof UpdateRemoteRunnerRequestSchema
>;

export const RemoteRunnerPairRequestSchema = z.strictObject({
  server_url: z.string(),
  name: z.string(),
});
export const RemoteRunnerTokenRequestSchema = z.strictObject({
  server_url: z.string(),
  token: z.string(),
});

/** Имя ИИ-адреса раннера: те же правила, что у сервера (ENDPOINT_NAME_RE). */
export const ENDPOINT_NAME_RE = /^[a-z0-9][a-z0-9_-]{0,31}$/;

/** Код сопряжения XXXX-XXXX из алфавита без похожих букв. */
export const USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789";
