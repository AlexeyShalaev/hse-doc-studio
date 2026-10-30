import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import {
  isValidServerUrl,
  normalizeUserCode,
  type MyRunnerTokenCreated,
  type ProjectBuildRunners,
  type RemoteAiEndpoint,
  type RunnerPairingInfo,
} from "@entities/runner";
import {
  DEMO_SERVER_URL,
  ownProviderView,
  registeredRunner,
  relayState,
  runnerState,
  toMyRunner,
  type DemoPairing,
  type DemoPersonal,
  type DemoRunnerOwner,
} from "./personalRunners";
import { effectiveRole } from "./projectAccess";
import { personalOf, type ServerDemoWorld } from "./world";

// Демо личных раннеров (/api/v1): мои раннеры и токены, сопряжение по коду,
// политика сборок проекта и облачные сборки локальной Студии. Правила как у
// настоящего API (раздел 9 спецификации): чужой раннер и токен неотличимы от
// несуществующих (404), секрет виден только в ответе на создание и смену токена,
// при выключенных личных раннерах создание даёт 403 personal_runners_disabled.
//
// Особые значения, чтобы вызывать каждое состояние руками:
//  - через несколько секунд после создания токена появляется раннер с его меткой
//    (будто его запустили), так же после подтверждения кода сопряжения;
//  - метка токена, начинающаяся с limit, отвечает 409 personal_runner_limit;
//  - коды сопряжения: BCDF-2345 ждёт, LMNP-6789 упирается в предел, XKCD-7777
//    истёк, QRST-2468 уже использован, остальные не найдены;
//  - адрес сервера с unreachable не отвечает (502), с disabled отвечает
//    remote_runner_disabled (409); токен не на hsrt_ отвечает 422.

const SECOND = 1000;
const MINUTE = 60 * SECOND;
// Через столько «запущенный» раннер регистрируется и попадает в список.
const REGISTER_AFTER_MS = 6 * SECOND;
// Через столько Студия «видит» подтверждение кода и подключается.
const PAIRING_DONE_MS = 8 * SECOND;
const PAIRING_TTL_MS = 10 * MINUTE;
const TOKEN_LIMIT = 5;
const NAME_MAX = 128;
const REVOKED_VISIBLE_MS = 30 * 24 * 60 * MINUTE;

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const unauth = () => demoError(401, "auth_required", "Authentication required");
const notFound = () => demoError(404, "not_found", "Not Found");
const invalid = () => demoError(422, "input_invalid", "Invalid input");
const disabled = () =>
  demoError(
    403,
    "personal_runners_disabled",
    "Personal runners are turned off on this installation",
  );

const secret = (prefix: string): string =>
  `${prefix}_${Math.random().toString(36).slice(2, 14)}${Math.random()
    .toString(36)
    .slice(2, 12)}`;

const tokenCommand = (value: string): string =>
  `HSE_RUNNER__API_URL=${DEMO_SERVER_URL} HSE_RUNNER__TOKEN=${value} hse-doc-studio runner`;

const dockerCommand = (value: string): string =>
  [
    "docker run -d --name hse-runner --restart unless-stopped",
    '--group-add "$(stat -c %g /var/run/docker.sock)"',
    "-v /var/run/docker.sock:/var/run/docker.sock",
    "-v /var/lib/hse-runner:/var/lib/hse-runner",
    `-e HSE_RUNNER__API_URL=${DEMO_SERVER_URL} -e HSE_RUNNER__TOKEN=${value}`,
    "-e HSE_RUNNER__DATA_DIR=/var/lib/hse-runner",
    "ghcr.io/alexeyshalaev/hse-doc-studio:0.3.0 hse-doc-studio runner",
  ].join(" ");

const runnerCommand = (value: string): string =>
  `HSE_RUNNER__API_URL=${DEMO_SERVER_URL} HSE_RUNNER__RUNNER_TOKEN=${value} hse-doc-studio runner`;

/** Токены, по которым раннер уже «запустился»: превращаем их в раннеры. */
const materialize = (state: DemoPersonal, owner: DemoRunnerOwner): void => {
  const now = Date.now();
  for (const token of state.tokens) {
    if (token.owner_id !== owner.id || token.registers_at === null) continue;
    if (token.revoked || now < token.registers_at) continue;
    token.registers_at = null;
    token.used = true;
    state.runners.unshift(
      registeredRunner(state, owner, token.label || "Новый раннер", "cli"),
    );
  }
};

const pairingInfo = ({
  hits_limit: _limit,
  ...info
}: DemoPairing): RunnerPairingInfo => info;

// Решённый код остаётся решённым и после срока: повтор даёт «уже использован».
const isExpired = (pairing: DemoPairing): boolean =>
  pairing.status === "expired" ||
  (pairing.status === "pending" && Date.parse(pairing.expires_at) < Date.now());

export const createPersonalRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const state = () => personalOf(getWorld());

  /** Вошедший человек как хозяин раннеров; null, если входа нет. */
  const me = (): DemoRunnerOwner | null => {
    const user = getWorld().bootstrap.user;
    return user ? { id: user.id, name: user.name, email: user.email } : null;
  };

  const signedIn =
    (
      handler: (
        owner: DemoRunnerOwner,
        req: Parameters<DemoRoute["handler"]>[0],
      ) => DemoResponse,
    ): DemoRoute["handler"] =>
    (req) => {
      const owner = me();
      return owner ? handler(owner, req) : unauth();
    };

  const myRunner = (owner: DemoRunnerOwner, id: string | undefined) =>
    state().runners.find((r) => r.id === id && r.owner.id === owner.id);

  const body = (req: { body?: unknown }): Record<string, unknown> =>
    (req.body ?? {}) as Record<string, unknown>;

  const buildRunners = (
    projectId: string | undefined,
    owner: DemoRunnerOwner,
  ): ProjectBuildRunners | null => {
    const world = getWorld();
    const project = world.projects.find((p) => p.summary.id === projectId);
    if (!project || effectiveRole(world, project, owner.id) === null) {
      return null;
    }
    const s = state();
    const projectOwner = project.summary.owner;
    if (projectOwner.kind === "org") {
      return {
        policy: "shared",
        editable: false,
        project_kind: "org",
        personal_runners_enabled: s.enabled,
        my_builds: "shared",
        wait_s: s.waitS,
        owner_runners: [],
      };
    }
    const policy = s.policies[project.summary.id] ?? "shared";
    const isOwner = projectOwner.id === owner.id;
    const ownerRunners = s.runners
      .filter((r) => r.owner.id === projectOwner.id && r.revoked_at === null)
      .map((r) => ({ name: r.name, state: runnerState(r, s.enabled) }))
      .map((r) => ({
        name: r.name,
        state: r.state === "revoked" ? ("offline" as const) : r.state,
      }));
    const routed = isOwner || policy === "owner";
    return {
      policy,
      editable: isOwner,
      project_kind: "personal",
      personal_runners_enabled: s.enabled,
      my_builds:
        s.enabled && routed && ownerRunners.length > 0
          ? "personal_first"
          : "shared",
      wait_s: s.waitS,
      owner_runners: ownerRunners,
    };
  };

  const remoteView = () => {
    const remote = state().remote;
    if (
      remote.state === "pairing" &&
      remote.pairing_done_at !== null &&
      Date.now() >= remote.pairing_done_at
    ) {
      Object.assign(remote, {
        state: "online",
        paired: true,
        runner_id: "9f8e7d6c5b4a43210fedcba98765studio",
        pairing: null,
        pairing_done_at: null,
      });
    }
    const { pairing_done_at: _done, ...view } = remote;
    return view;
  };

  const endpointsOf = (choices: unknown): RemoteAiEndpoint[] | null => {
    if (!Array.isArray(choices)) return null;
    const out: RemoteAiEndpoint[] = [];
    for (const raw of choices as Record<string, unknown>[]) {
      const provider = state().localProviders.find(
        (p) => p.id === str(raw.provider_id),
      );
      const name = str(raw.name);
      if (!provider || provider.type === "claude" || name === "") return null;
      out.push({
        name,
        provider_id: provider.id,
        flavor: provider.type === "ollama" ? "ollama" : "openai",
        url: provider.base_url,
        announced: false,
      });
    }
    return out;
  };

  const serverUrlProblem = (url: string): DemoResponse | null => {
    if (!isValidServerUrl(url)) {
      return demoError(
        422,
        "remote_runner_url_invalid",
        "The server address must use https",
      );
    }
    if (url.includes("unreachable")) {
      return demoError(
        502,
        "remote_runner_unreachable",
        "The server did not respond",
      );
    }
    if (url.includes("disabled")) {
      return demoError(
        409,
        "remote_runner_disabled",
        "Personal runners are turned off on the server",
      );
    }
    return null;
  };

  // Свои провайдеры живут в демо только в мирах с личными раннерами; в
  // остальных сценариях запрос уходит дальше, как до этого среза.
  const inPersonalWorld =
    (handler: DemoRoute["handler"]): DemoRoute["handler"] =>
    (req) =>
      getWorld().scenario.personalSeed === undefined
        ? req.forward().then((res) => ({
            status: res.status,
            data: res.data as unknown,
          }))
        : handler(req);

  const ownProvider = (owner: DemoRunnerOwner, id: string | undefined) =>
    state().providers.find((p) => p.id === id && p.owner_id === owner.id);

  return [
    // Свои ИИ-провайдеры: прямые со своим ключом и «через мой раннер».
    // Провайдера на чужой раннер или на адрес, которого раннер не объявил,
    // создать нельзя (422 ai_provider_runner_invalid).
    {
      method: "POST",
      pattern: "/ai-providers",
      handler: inPersonalWorld(
        signedIn((owner, req) => {
          const s = state();
          const b = body(req);
          const type = str(b.type);
          const name = str(b.name).trim();
          if (name === "") return invalid();
          if (!["claude", "openai", "openai_compat", "runner"].includes(type)) {
            return invalid();
          }
          let runnerId: string | null = null;
          let endpoint: string | null = null;
          if (type === "runner") {
            const runner = myRunner(owner, str(b.runner_id));
            endpoint = str(b.runner_endpoint);
            if (
              runner?.revoked_at !== null ||
              !runner.ai_endpoints.some((e) => e.name === endpoint)
            ) {
              return demoError(
                422,
                "ai_provider_runner_invalid",
                "Pick your own runner and an endpoint it declared",
              );
            }
            runnerId = runner.id;
          } else if (str(b.api_key) === "") {
            return invalid();
          }
          s.counter += 1;
          const provider = {
            id: `7c6b5a49-3e2d-4c1b-8a09-${String(s.counter).padStart(12, "0")}`,
            owner_id: owner.id,
            name,
            type: type as "claude" | "openai" | "openai_compat" | "runner",
            base_url: type === "runner" ? "" : str(b.base_url),
            models: Array.isArray(b.models) ? (b.models as string[]) : [],
            has_api_key: type !== "runner",
            created_at: new Date().toISOString(),
            ssl_verify: b.ssl_verify !== false,
            connect_timeout_s:
              typeof b.connect_timeout_s === "number"
                ? b.connect_timeout_s
                : 10,
            request_timeout_s:
              typeof b.request_timeout_s === "number"
                ? b.request_timeout_s
                : 60,
            runner_id: runnerId,
            runner_endpoint: endpoint,
          };
          s.providers.unshift(provider);
          return demoJson(ownProviderView(s, provider), 201);
        }),
      ),
    },
    {
      method: "PATCH",
      pattern: "/ai-providers/:id",
      handler: inPersonalWorld(
        signedIn((owner, req) => {
          const provider = ownProvider(owner, req.params.id);
          if (!provider) return notFound();
          const b = body(req);
          if (typeof b.name === "string" && b.name.trim() !== "") {
            provider.name = b.name.trim();
          }
          if (Array.isArray(b.models)) provider.models = b.models as string[];
          if (typeof b.request_timeout_s === "number") {
            provider.request_timeout_s = b.request_timeout_s;
          }
          if (typeof b.base_url === "string" && provider.type !== "runner") {
            provider.base_url = b.base_url;
          }
          return demoJson(ownProviderView(state(), provider));
        }),
      ),
    },
    {
      method: "DELETE",
      pattern: "/ai-providers/:id",
      handler: inPersonalWorld(
        signedIn((owner, req) => {
          const s = state();
          const provider = ownProvider(owner, req.params.id);
          if (!provider) return notFound();
          s.providers = s.providers.filter((p) => p !== provider);
          return demoNoContent();
        }),
      ),
    },
    {
      method: "GET",
      pattern: "/ai-providers/:id/models",
      handler: inPersonalWorld(
        signedIn((owner, req) => {
          const s = state();
          const provider = ownProvider(owner, req.params.id);
          if (!provider) return notFound();
          if (provider.type !== "runner") {
            return demoJson({ models: provider.models });
          }
          // Модели знает только модель за раннером: без готового раннера 503.
          if (relayState(s, provider) !== "ready") {
            return demoError(
              503,
              "relay_unavailable",
              "The runner did not respond",
            );
          }
          return demoJson({
            models: ["qwen2.5:7b", "llama3.1:8b", "mistral-nemo:12b"],
          });
        }),
      ),
    },
    {
      method: "GET",
      pattern: "/account/runners",
      handler: signedIn((owner) => {
        const s = state();
        materialize(s, owner);
        const now = Date.now();
        return demoJson(
          s.runners
            .filter((r) => r.owner.id === owner.id)
            .filter(
              (r) =>
                r.revoked_at === null ||
                now - Date.parse(r.revoked_at) < REVOKED_VISIBLE_MS,
            )
            .map((r) => toMyRunner(r, s.enabled)),
        );
      }),
    },
    {
      method: "PATCH",
      pattern: "/account/runners/:id",
      handler: signedIn((owner, req) => {
        const r = myRunner(owner, req.params.id);
        if (!r) return notFound();
        const b = body(req);
        if (typeof b.name === "string") {
          const name = b.name.replace(/\s+/g, " ").trim();
          if (name === "" || name.length > NAME_MAX) return invalid();
          r.name = name;
        }
        if (typeof b.paused === "boolean") {
          if (r.revoked_at !== null) {
            return demoError(409, "runner_revoked", "The runner is revoked");
          }
          if (!b.paused && r.paused && r.paused_by === "admin") {
            return demoError(
              403,
              "runner_paused_by_admin",
              "An administrator paused this runner",
            );
          }
          r.paused = b.paused;
          r.paused_by = b.paused ? "owner" : null;
        }
        return demoJson(toMyRunner(r, state().enabled));
      }),
    },
    {
      method: "POST",
      pattern: "/account/runners/:id/rotate-token",
      handler: signedIn((owner, req) => {
        const r = myRunner(owner, req.params.id);
        if (!r) return notFound();
        if (r.revoked_at !== null) {
          return demoError(409, "runner_revoked", "The runner is revoked");
        }
        const value = secret("hsrn");
        return demoJson({
          runner: toMyRunner(r, state().enabled),
          runner_token: value,
          command: runnerCommand(value),
        });
      }),
    },
    {
      method: "DELETE",
      pattern: "/account/runners/:id",
      handler: signedIn((owner, req) => {
        const r = myRunner(owner, req.params.id);
        if (!r) return notFound();
        r.revoked_at ??= new Date().toISOString();
        r.alive = false;
        r.running_jobs = 0;
        return demoNoContent();
      }),
    },
    {
      method: "GET",
      pattern: "/account/runner-tokens",
      handler: signedIn((owner) => {
        const s = state();
        materialize(s, owner);
        return demoJson(
          s.tokens
            .filter((t) => t.owner_id === owner.id && !t.revoked)
            .map(({ owner_id: _o, registers_at: _r, ...token }) => token),
        );
      }),
    },
    {
      method: "POST",
      pattern: "/account/runner-tokens",
      handler: signedIn((owner, req) => {
        const s = state();
        if (!s.enabled) return disabled();
        const b = body(req);
        const label = str(b.label).trim();
        const ttl = b.ttl_hours;
        if (
          label.length > NAME_MAX ||
          typeof ttl !== "number" ||
          !Number.isInteger(ttl) ||
          ttl < 1 ||
          ttl > 168
        ) {
          return invalid();
        }
        const open = s.tokens.filter(
          (t) => t.owner_id === owner.id && !t.used && !t.revoked,
        );
        if (
          label.toLowerCase().startsWith("limit") ||
          open.length >= TOKEN_LIMIT
        ) {
          return demoError(
            409,
            "personal_runner_limit",
            "Too many personal runners or unused tokens",
          );
        }
        s.counter += 1;
        const now = Date.now();
        const value = secret("hsrt");
        const token = {
          id: `8a7b6c5d4e3f4011223344556677${String(s.counter).padStart(4, "0")}`,
          label,
          created_at: new Date(now).toISOString(),
          expires_at: new Date(now + ttl * 60 * MINUTE).toISOString(),
          used: false,
          revoked: false,
        };
        s.tokens.unshift({
          ...token,
          owner_id: owner.id,
          registers_at: now + REGISTER_AFTER_MS,
        });
        const created: MyRunnerTokenCreated = {
          token,
          secret: value,
          command: tokenCommand(value),
          docker_command: dockerCommand(value),
        };
        return demoJson(created, 201);
      }),
    },
    {
      method: "DELETE",
      pattern: "/account/runner-tokens/:id",
      handler: signedIn((owner, req) => {
        const token = state().tokens.find(
          (t) => t.id === req.params.id && t.owner_id === owner.id,
        );
        if (!token) return notFound();
        token.revoked = true;
        token.registers_at = null;
        return demoNoContent();
      }),
    },
    {
      method: "GET",
      pattern: "/account/runner-pairings/:code",
      handler: signedIn((_owner, req) => {
        const code = normalizeUserCode(str(req.params.code));
        const pairing = code ? state().pairings[code] : undefined;
        if (!pairing) {
          return demoError(404, "runner_pairing_invalid", "Unknown code");
        }
        if (isExpired(pairing)) {
          return demoError(410, "runner_pairing_expired", "The code expired");
        }
        return demoJson(pairingInfo(pairing));
      }),
    },
    {
      method: "POST",
      pattern: "/account/runner-pairings/:code",
      handler: signedIn((owner, req) => {
        const s = state();
        const code = normalizeUserCode(str(req.params.code));
        const pairing = code ? s.pairings[code] : undefined;
        const decision = str(body(req).decision);
        if (decision !== "approve" && decision !== "deny") return invalid();
        if (!pairing) {
          return demoError(404, "runner_pairing_invalid", "Unknown code");
        }
        if (isExpired(pairing)) {
          return demoError(410, "runner_pairing_expired", "The code expired");
        }
        if (pairing.status !== "pending") {
          return demoError(409, "runner_pairing_used", "The code was used");
        }
        if (decision === "approve") {
          if (!s.enabled) return disabled();
          if (pairing.hits_limit) {
            return demoError(
              409,
              "personal_runner_limit",
              "Too many personal runners",
            );
          }
          pairing.status = "approved";
          s.runners.unshift(
            registeredRunner(s, owner, pairing.name, pairing.host_kind),
          );
        } else {
          pairing.status = "denied";
        }
        return demoJson(pairingInfo(pairing));
      }),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/build-runners",
      handler: signedIn((owner, req) => {
        const info = buildRunners(req.params.projectId, owner);
        return info ? demoJson(info) : notFound();
      }),
    },
    {
      method: "PUT",
      pattern: "/projects/:projectId/build-runners",
      handler: signedIn((owner, req) => {
        const info = buildRunners(req.params.projectId, owner);
        if (!info) return notFound();
        if (info.project_kind === "org") {
          return demoError(
            409,
            "project_not_personal",
            "Organization projects build on shared runners",
          );
        }
        if (!info.editable) {
          return demoError(403, "forbidden_role", "Owner role required", {
            required_role: "owner",
          });
        }
        const policy = str(body(req).policy);
        if (policy !== "shared" && policy !== "owner") return invalid();
        state().policies[req.params.projectId ?? ""] = policy;
        return demoJson(buildRunners(req.params.projectId, owner));
      }),
    },
    {
      method: "GET",
      pattern: "/remote-runner",
      handler: () => demoJson(remoteView()),
    },
    {
      method: "PUT",
      pattern: "/remote-runner",
      handler: (req) => {
        const remote = state().remote;
        const b = body(req);
        if (typeof b.server_url === "string") {
          const problem = isValidServerUrl(b.server_url)
            ? null
            : serverUrlProblem(b.server_url);
          if (problem) return problem;
          remote.server_url = b.server_url.trim();
        }
        if (typeof b.name === "string" && b.name.trim() !== "") {
          remote.runner_name = b.name.trim();
        }
        if (typeof b.concurrency === "number") {
          if (b.concurrency < 1 || b.concurrency > 4) return invalid();
          remote.concurrency = b.concurrency;
        }
        if (typeof b.yield_to_local === "boolean") {
          remote.yield_to_local = b.yield_to_local;
        }
        if (b.ai_endpoints != null) {
          const endpoints = endpointsOf(b.ai_endpoints);
          if (!endpoints) return invalid();
          remote.ai_endpoints = endpoints;
        }
        if (typeof b.enabled === "boolean") {
          remote.enabled = b.enabled;
          if (!b.enabled) {
            remote.state = "off";
            remote.pairing = null;
            remote.pairing_done_at = null;
            remote.running_jobs = 0;
          } else {
            remote.state = remote.paired ? "online" : "unpaired";
          }
        }
        return demoJson(remoteView());
      },
    },
    {
      method: "POST",
      pattern: "/remote-runner/pair",
      handler: (req) => {
        const remote = state().remote;
        const b = body(req);
        const url = str(b.server_url).trim();
        const problem = serverUrlProblem(url);
        if (problem) return problem;
        const now = Date.now();
        Object.assign(remote, {
          enabled: true,
          server_url: url,
          runner_name: str(b.name).trim() || "MacBook Анны",
          state: "pairing",
          detail_code: null,
          pairing: {
            user_code: "BCDF-2345",
            verification_uri_complete: `${url.replace(/\/$/, "")}/settings/runners/pair?code=BCDF-2345`,
            expires_at: new Date(now + PAIRING_TTL_MS).toISOString(),
          },
          pairing_done_at: now + PAIRING_DONE_MS,
        });
        return demoJson(remoteView());
      },
    },
    {
      method: "POST",
      pattern: "/remote-runner/token",
      handler: (req) => {
        const remote = state().remote;
        const b = body(req);
        const url = str(b.server_url).trim();
        const problem = serverUrlProblem(url);
        if (problem) return problem;
        if (!str(b.token).startsWith("hsrt_")) return invalid();
        Object.assign(remote, {
          enabled: true,
          server_url: url,
          paired: true,
          runner_id: "9f8e7d6c5b4a43210fedcba98765token",
          runner_name: remote.runner_name ?? "MacBook Анны",
          state: "online",
          detail_code: null,
          pairing: null,
          pairing_done_at: null,
        });
        return demoJson(remoteView());
      },
    },
    {
      method: "DELETE",
      pattern: "/remote-runner/pairing",
      handler: () => {
        Object.assign(state().remote, {
          state: "unpaired",
          pairing: null,
          pairing_done_at: null,
        });
        return demoJson(remoteView());
      },
    },
    {
      method: "DELETE",
      pattern: "/remote-runner",
      handler: () => {
        Object.assign(state().remote, {
          enabled: false,
          paired: false,
          runner_id: null,
          state: "off",
          running_jobs: 0,
          pairing: null,
          pairing_done_at: null,
        });
        return demoJson(remoteView());
      },
    },
  ];
};
