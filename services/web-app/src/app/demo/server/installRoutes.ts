import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type { AdminSettingState } from "@entities/session";
import type { DemoSharedProvider } from "./adminInstall";
import { adminInstallOf, type ServerDemoWorld } from "./world";

// Демо админки: название и адрес, сборка, политика ключей подписи, общие ИИ-провайдеры.
// Тела совпадают с contracts/server/fixtures. Правила как у настоящего API: только админ
// установки (остальным 404), значения окружения не меняются (409 setting_locked), ключ
// провайдера принимается на запись и не возвращается.
//
// Особые значения: имя провайдера с limit в начале даёт 429 rate_limited; имя с fail в начале
// не проходит проверку моделей; публичный адрес не https (кроме localhost) даёт 422.

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const notFound = () => demoError(404, "not_found", "Not Found");
const invalid = () => demoError(422, "input_invalid", "Invalid input");
const locked = () =>
  demoError(409, "setting_locked", "The value is set by the environment");

const admin = (): AdminSettingState => ({ source: "admin", locked: false });

const isHttpUrl = (value: string, secureOnly: boolean): boolean => {
  try {
    const url = new URL(value);
    if (url.hostname === "") return false;
    if (url.protocol === "https:") return true;
    return (
      !secureOnly ||
      (url.protocol === "http:" &&
        ["localhost", "127.0.0.1"].includes(url.hostname))
    );
  } catch {
    return false;
  }
};

const TYPES = ["claude", "openai", "openai_compat"] as const;

export const createInstallRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const guard = (): DemoResponse | null => {
    const { user } = getWorld().bootstrap;
    if (user === null)
      return demoError(401, "auth_required", "Authentication required");
    return user.is_instance_admin
      ? null
      : demoError(404, "not_found", "Not Found");
  };
  const guarded =
    (handler: DemoRoute["handler"]): DemoRoute["handler"] =>
    (req) =>
      guard() ?? handler(req);
  const state = () => adminInstallOf(getWorld());

  /** Пользователь узнаёт политику из bootstrap: держим его в согласии с админкой. */
  const syncBootstrap = () => {
    const world = getWorld();
    world.bootstrap = {
      ...world.bootstrap,
      capabilities: {
        ...world.bootstrap.capabilities,
        personal_signing_keys: state().signing.server_keys === "allowed",
      },
    };
  };

  const providerFrom = (
    body: Record<string, unknown>,
    base: DemoSharedProvider,
  ): DemoSharedProvider | null => {
    const next = { ...base };
    if (typeof body.name === "string") next.name = body.name.trim();
    if (
      typeof body.type === "string" &&
      (TYPES as readonly string[]).includes(body.type)
    ) {
      next.type = body.type as DemoSharedProvider["type"];
    }
    if (typeof body.base_url === "string") next.base_url = body.base_url.trim();
    if (Array.isArray(body.models)) next.models = body.models.map(str);
    if (typeof body.ssl_verify === "boolean") next.ssl_verify = body.ssl_verify;
    if (typeof body.connect_timeout_s === "number") {
      next.connect_timeout_s = body.connect_timeout_s;
    }
    if (typeof body.request_timeout_s === "number") {
      next.request_timeout_s = body.request_timeout_s;
    }
    if (typeof body.api_key === "string" && body.api_key !== "") {
      next.key_set = true;
    }
    if (body.clear_key === true) next.key_set = false;
    if (next.name === "") return null;
    if (next.type === "openai_compat" && next.base_url === "") return null;
    return next;
  };

  return [
    {
      method: "GET",
      pattern: "/settings/instance",
      handler: guarded(() => demoJson(state().instance)),
    },
    {
      method: "PUT",
      pattern: "/settings/instance",
      handler: guarded((req) => {
        const s = state();
        const body = (req.body ?? {}) as Record<string, unknown>;
        const f = s.instance.fields;
        for (const key of ["name", "public_url", "docs_url"] as const) {
          if (body[key] != null && f[`instance.${key}`]?.locked)
            return locked();
        }
        const next = { ...s.instance };
        const fields = { ...f };
        if (typeof body.name === "string") {
          const name = body.name.trim();
          if (name === "" || name.length > 120) return invalid();
          next.name = name;
          fields["instance.name"] = admin();
        }
        if (typeof body.public_url === "string") {
          if (!isHttpUrl(body.public_url.trim(), true)) return invalid();
          next.public_url = body.public_url.trim();
          fields["instance.public_url"] = admin();
        }
        if (typeof body.docs_url === "string") {
          const docs = body.docs_url.trim();
          if (docs !== "" && !isHttpUrl(docs, false)) return invalid();
          next.docs_url = docs === "" ? null : docs;
          fields["instance.docs_url"] = admin();
        }
        s.instance = { ...next, fields };
        return demoJson(s.instance);
      }),
    },
    {
      method: "GET",
      pattern: "/settings/build",
      handler: guarded(() => demoJson(state().build)),
    },
    {
      method: "PUT",
      pattern: "/settings/build",
      handler: guarded((req) => {
        const s = state();
        const body = (req.body ?? {}) as Record<string, unknown>;
        const f = s.build.fields;
        if (body.timeout_s != null && f["build.timeout_s"]?.locked) {
          return locked();
        }
        if (
          body.artifact_retention_days != null &&
          f["build.artifact_retention_days"]?.locked
        ) {
          return locked();
        }
        const next = { ...s.build };
        const fields = { ...f };
        if (typeof body.timeout_s === "number") {
          if (
            !Number.isInteger(body.timeout_s) ||
            body.timeout_s < 30 ||
            body.timeout_s > 3600
          ) {
            return invalid();
          }
          next.timeout_s = body.timeout_s;
          fields["build.timeout_s"] = admin();
        }
        if (typeof body.artifact_retention_days === "number") {
          const days = body.artifact_retention_days;
          if (!Number.isInteger(days) || days < 1 || days > 365) {
            return invalid();
          }
          next.artifact_retention_days = days;
          fields["build.artifact_retention_days"] = admin();
        }
        s.build = { ...next, fields };
        return demoJson(s.build);
      }),
    },
    {
      method: "GET",
      pattern: "/settings/signing",
      handler: guarded(() => demoJson(state().signing)),
    },
    {
      method: "PUT",
      pattern: "/settings/signing",
      handler: guarded((req) => {
        const s = state();
        const { server_keys: value } = (req.body ?? {}) as Record<
          string,
          unknown
        >;
        if (value == null) return demoJson(s.signing);
        if (value !== "allowed" && value !== "forbidden") return invalid();
        // Ключи не стираются: при запрете они лишь блокируются.
        s.signing = { ...s.signing, server_keys: value };
        syncBootstrap();
        return demoJson(s.signing);
      }),
    },
    {
      method: "GET",
      pattern: "/ai-providers",
      handler: guarded(() => demoJson(state().providers)),
    },
    {
      method: "POST",
      pattern: "/ai-providers",
      handler: guarded((req) => {
        const body = (req.body ?? {}) as Record<string, unknown>;
        if (str(body.name).trim().toLowerCase().startsWith("limit")) {
          return demoError(429, "rate_limited", "Too many requests", {
            retry_after: 20,
          });
        }
        if (str(body.api_key) === "") return invalid();
        const s = state();
        const created = providerFrom(body, {
          id: `aip_${Math.random().toString(36).slice(2, 10)}`,
          name: "",
          type: "claude",
          base_url: "",
          models: [],
          key_set: false,
          created_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
          ssl_verify: true,
          connect_timeout_s: 10,
          request_timeout_s: 60,
        });
        if (!created) return invalid();
        s.providers = [...s.providers, created];
        return demoJson(created, 201);
      }),
    },
    {
      method: "PATCH",
      pattern: "/ai-providers/:id",
      handler: guarded((req) => {
        const s = state();
        const current = s.providers.find((p) => p.id === req.params.id);
        if (!current) return notFound();
        const updated = providerFrom(
          (req.body ?? {}) as Record<string, unknown>,
          current,
        );
        if (!updated) return invalid();
        s.providers = s.providers.map((p) =>
          p.id === current.id ? updated : p,
        );
        return demoJson(updated);
      }),
    },
    {
      method: "DELETE",
      pattern: "/ai-providers/:id",
      handler: guarded((req) => {
        const s = state();
        if (!s.providers.some((p) => p.id === req.params.id)) {
          return notFound();
        }
        s.providers = s.providers.filter((p) => p.id !== req.params.id);
        return demoNoContent();
      }),
    },
    {
      method: "POST",
      pattern: "/ai-providers/:id/check",
      handler: guarded((req) => {
        const found = state().providers.find((p) => p.id === req.params.id);
        if (!found) return notFound();
        // Сбой провайдера приходит ответом ok=false, а не ошибкой запроса.
        if (found.name.toLowerCase().startsWith("fail")) {
          return demoJson({ ok: false, models: [], error: "ConnectError" });
        }
        return demoJson({
          ok: true,
          models: ["model-large", "model-small"],
          error: null,
        });
      }),
    },
  ];
};

/**
 * Маршрут пользователя (/api/v1): общие провайдеры в его списке. Ключа в ответе нет,
 * `shared: true` отличает их от личных.
 */
export const createSharedProviderUserRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  {
    method: "GET",
    pattern: "/ai-providers",
    handler: () => {
      const world = getWorld();
      if (world.bootstrap.user === null) {
        return demoError(401, "auth_required", "Authentication required");
      }
      return demoJson(
        adminInstallOf(world).providers.map(
          ({ key_set: _keySet, ...rest }) => ({
            ...rest,
            // Ключа пользователь не видит, но запись общая.
            has_api_key: true,
            shared: true,
          }),
        ),
      );
    },
  },
];
