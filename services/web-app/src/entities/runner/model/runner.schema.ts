import { z } from "zod";

// Личные раннеры: аккаунт, сопряжение, политика сборок проекта, размещение сборки и локальная Студия
// как раннер. Формы совпадают с contracts/server/fixtures и api/schemas/{personal_runners,remote_runner}.py.

const iso = z.string().min(1);

export const RunnerHostKindSchema = z.enum(["cli", "desktop"]);
export const AiEndpointFlavorSchema = z.enum(["openai", "ollama"]);

export const MyRunnerStateSchema = z.enum([
  "online",
  "stale",
  "offline",
  "paused",
  "revoked",
  "disabled",
]);
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
  ai_endpoints: z.array(
    z.strictObject({ name: z.string(), flavor: AiEndpointFlavorSchema }),
  ),
  features: z.array(z.string()),
});
export const MyRunnerListSchema = z.array(MyRunnerSchema);
export const UpdateMyRunnerRequestSchema = z.strictObject({
  name: z.string().min(1).max(128).nullable(),
  paused: z.boolean().nullable(),
});
export const MyRunnerRotatedSchema = z.strictObject({
  runner: MyRunnerSchema,
  runner_token: z.string(),
  command: z.string(),
});

export const MyRunnerTokenSchema = z.strictObject({
  id: z.string(),
  label: z.string(),
  created_at: iso,
  expires_at: iso.nullable(),
  used: z.boolean(),
  revoked: z.boolean(),
});
export const MyRunnerTokenListSchema = z.array(MyRunnerTokenSchema);
export const CreateMyRunnerTokenRequestSchema = z.strictObject({
  label: z.string().max(128),
  ttl_hours: z.number().int().min(1).max(168),
});
export const MyRunnerTokenCreatedSchema = z.strictObject({
  token: MyRunnerTokenSchema,
  secret: z.string(),
  command: z.string(),
  docker_command: z.string(),
});

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
export const RunnerPairingDecisionRequestSchema = z.strictObject({
  decision: z.enum(["approve", "deny"]),
});

export const BuildRunnersPolicySchema = z.enum(["shared", "owner"]);
export const ProjectBuildRunnersSchema = z.strictObject({
  policy: BuildRunnersPolicySchema,
  editable: z.boolean(),
  project_kind: z.enum(["personal", "org"]),
  personal_runners_enabled: z.boolean(),
  my_builds: z.enum(["personal_first", "shared"]),
  wait_s: z.number().int(),
  owner_runners: z.array(
    z.strictObject({
      name: z.string(),
      state: z.enum(["online", "stale", "offline", "paused", "disabled"]),
    }),
  ),
});
export const UpdateProjectBuildRunnersRequestSchema = z.strictObject({
  policy: BuildRunnersPolicySchema,
});

export const CompilePlacementSchema = z.strictObject({
  state: z.enum(["waiting_personal", "personal", "shared"]),
  runner_name: z.string().nullable(),
  runner_owner: z.enum(["me", "owner"]).nullable(),
  fallback: z
    .enum(["offline", "busy", "timeout", "lost", "disabled"])
    .nullable(),
  wait_s: z.number().int().nullable(),
});

export const RemoteRunnerStateSchema = z.enum([
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
]);
export const RemoteRunnerStatusSchema = z.strictObject({
  enabled: z.boolean(),
  server_url: z.string().nullable(),
  paired: z.boolean(),
  runner_id: z.string().nullable(),
  runner_name: z.string().nullable(),
  state: RemoteRunnerStateSchema,
  detail_code: z.string().nullable(),
  running_jobs: z.number().int(),
  concurrency: z.number().int(),
  yield_to_local: z.boolean(),
  docker: z.enum(["ok", "missing"]),
  tex_image: z.enum(["ready", "missing"]),
  ai_endpoints: z.array(
    z.strictObject({
      name: z.string(),
      provider_id: z.string(),
      flavor: AiEndpointFlavorSchema,
      url: z.string(),
    }),
  ),
  pairing: z
    .strictObject({
      user_code: z.string(),
      verification_uri_complete: z.string(),
      expires_at: iso,
    })
    .nullable(),
});
export const UpdateRemoteRunnerRequestSchema = z.strictObject({
  enabled: z.boolean().nullable(),
  server_url: z.string().nullable(),
  name: z.string().min(1).max(128).nullable(),
  concurrency: z.number().int().min(1).max(4).nullable(),
  yield_to_local: z.boolean().nullable(),
  ai_endpoints: z
    .array(z.strictObject({ name: z.string(), provider_id: z.string() }))
    .nullable(),
});
export const RemoteRunnerPairRequestSchema = z.strictObject({
  server_url: z.string().min(1),
  name: z.string().min(1).max(128),
});
export const RemoteRunnerTokenRequestSchema = z.strictObject({
  server_url: z.string().min(1),
  token: z.string().min(1),
});

export type MyRunner = z.infer<typeof MyRunnerSchema>;
export type MyRunnerState = z.infer<typeof MyRunnerStateSchema>;
export type UpdateMyRunnerRequest = z.infer<typeof UpdateMyRunnerRequestSchema>;
export type MyRunnerRotated = z.infer<typeof MyRunnerRotatedSchema>;
export type MyRunnerToken = z.infer<typeof MyRunnerTokenSchema>;
export type CreateMyRunnerTokenRequest = z.infer<
  typeof CreateMyRunnerTokenRequestSchema
>;
export type MyRunnerTokenCreated = z.infer<typeof MyRunnerTokenCreatedSchema>;
export type RunnerPairingInfo = z.infer<typeof RunnerPairingInfoSchema>;
export type RunnerPairingDecisionRequest = z.infer<
  typeof RunnerPairingDecisionRequestSchema
>;
export type ProjectBuildRunners = z.infer<typeof ProjectBuildRunnersSchema>;
export type UpdateProjectBuildRunnersRequest = z.infer<
  typeof UpdateProjectBuildRunnersRequestSchema
>;
export type CompilePlacement = z.infer<typeof CompilePlacementSchema>;
export type RemoteRunnerState = z.infer<typeof RemoteRunnerStateSchema>;
export type RemoteRunnerStatus = z.infer<typeof RemoteRunnerStatusSchema>;
export type UpdateRemoteRunnerRequest = z.infer<
  typeof UpdateRemoteRunnerRequestSchema
>;
export type RemoteRunnerPairRequest = z.infer<
  typeof RemoteRunnerPairRequestSchema
>;
export type RemoteRunnerTokenRequest = z.infer<
  typeof RemoteRunnerTokenRequestSchema
>;
