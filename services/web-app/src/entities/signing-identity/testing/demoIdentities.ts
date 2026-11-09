import { demoError, demoJson, type DemoRoute } from "@shared/api/demo";
import type { SigningIdentity } from "../api/signingIdentitySchemas";

// Ключи Студии для серверного демо и тестов: список, ключ по умолчанию, создание и импорт.
// Состояние в памяти, по пользователям. Формы тел как у /signing-identities бэкенда.

export type SigningIdentityDemoUser = { id: string; name: string };

export type SigningIdentityDemoOptions = {
  /** Кто сейчас вошёл; null: 401. */
  getUser: () => SigningIdentityDemoUser | null;
  /** Политика установки: можно ли хранить закрытые ключи на сервере. */
  allowed?: () => boolean;
  now?: () => number;
};

export type SigningIdentityDemo = {
  routes: DemoRoute[];
  reset: () => void;
  /** Ключи пользователя: ключ по умолчанию первым. */
  keysOf: (userId: string) => SigningIdentity[];
  /** Положить готовый ключ (заготовка сценария). */
  add: (
    userId: string,
    key: Partial<SigningIdentity> & { label: string },
  ) => SigningIdentity;
};

const forbidden = () =>
  demoError(
    403,
    "server_keys_forbidden",
    "Private keys are not stored on this server",
  );

const field = (body: unknown, name: string): string => {
  if (typeof FormData !== "undefined" && body instanceof FormData) {
    const value = body.get(name);
    return typeof value === "string" ? value : "";
  }
  const value = (body as Record<string, unknown> | null)?.[name];
  return typeof value === "string" ? value : "";
};

const fileOf = (body: unknown): File | null => {
  if (typeof FormData === "undefined" || !(body instanceof FormData))
    return null;
  const value = body.get("file");
  return value instanceof File ? value : null;
};

export const createSigningIdentityDemo = (
  options: SigningIdentityDemoOptions,
): SigningIdentityDemo => {
  const allowed = options.allowed ?? (() => true);
  const clock = options.now ?? (() => Date.now());
  let store = new Map<string, SigningIdentity[]>();
  let seq = 0;

  const keysOf = (userId: string): SigningIdentity[] => store.get(userId) ?? [];

  const add: SigningIdentityDemo["add"] = (userId, key) => {
    seq += 1;
    const tail = String(seq).padStart(12, "0");
    const identity: SigningIdentity = {
      id: `00000000-0000-4000-8000-${tail}`,
      kind: "openpgp",
      subject_cn: key.label,
      not_after: new Date(clock() + 2 * 365 * 86_400_000).toISOString(),
      trusted: false,
      created_at: new Date(clock()).toISOString(),
      fingerprint: `1A2B3C4D5E6F7A8B9C0D${tail}`.padEnd(40, "0").slice(0, 40),
      protected: false,
      ...key,
    };
    store.set(userId, [...keysOf(userId), identity]);
    return identity;
  };

  const guarded =
    (
      handler: (
        user: SigningIdentityDemoUser,
        body: unknown,
      ) => ReturnType<DemoRoute["handler"]>,
      write = true,
    ): DemoRoute["handler"] =>
    (req) => {
      const user = options.getUser();
      if (!user)
        return demoError(401, "auth_required", "Authentication required");
      if (write && !allowed()) return forbidden();
      return handler(user, req.body);
    };

  const routes: DemoRoute[] = [
    {
      method: "GET",
      pattern: "/signing-identities",
      handler: guarded(
        (user) => demoJson(allowed() ? keysOf(user.id) : []),
        false,
      ),
    },
    {
      method: "GET",
      pattern: "/signing-identities/default",
      handler: guarded((user) => {
        const first = allowed() ? (keysOf(user.id)[0]?.id ?? null) : null;
        return demoJson({
          identity_id: null,
          effective_id: first,
          auto: first !== null,
        });
      }, false),
    },
    {
      method: "POST",
      pattern: "/signing-identities/openpgp/generate",
      handler: guarded((user, body) => {
        const name = field(body, "name").trim();
        if (name === "")
          return demoError(422, "validation_error", "name is required");
        return demoJson(
          add(user.id, {
            label: field(body, "label") || `OpenPGP: ${name}`,
            subject_cn: name,
            protected: field(body, "passphrase") !== "",
          }),
        );
      }),
    },
    {
      method: "POST",
      pattern: "/signing-identities/openpgp/import",
      handler: guarded((user, body) => {
        const file = fileOf(body);
        if (!file)
          return demoError(422, "validation_error", "file is required");
        // Файл только с открытым ключом: закрытой части нет, подписывать нечем.
        if (/pub/i.test(file.name))
          return demoJson({ identities: [], public_keys: [] });
        return demoJson({
          identities: [
            add(user.id, {
              label: file.name.replace(/\.[^.]+$/, ""),
              protected: field(body, "passphrase") !== "",
            }),
          ],
          public_keys: [],
        });
      }),
    },
    {
      method: "POST",
      pattern: "/signing-identities/import-pkcs12",
      handler: guarded((user, body) => {
        const file = fileOf(body);
        if (!file)
          return demoError(422, "validation_error", "file is required");
        // Как бэкенд сейчас: отказ без кода, только с пояснением.
        if (field(body, "passphrase") === "wrong")
          return demoError(
            400,
            "unknown_error",
            "Неверный пароль контейнера .p12",
          );
        return demoJson(
          add(user.id, {
            label: field(body, "label") || file.name,
            kind: "pkcs12",
            protected: field(body, "passphrase") !== "",
          }),
        );
      }),
    },
  ];

  return {
    routes,
    reset: () => {
      store = new Map();
      seq = 0;
    },
    keysOf,
    add,
  };
};
