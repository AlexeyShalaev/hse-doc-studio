import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import { validateEmail } from "@entities/profile";
import { effectiveOf } from "./accounts";
import { accountOf, signOut, type ServerDemoWorld } from "./world";

// Демо аккаунта: профиль и подпись версий, смена пароля и почты, сессии.
// Тела совпадают с contracts/server/fixtures (AccountProfile, AccountSession...).
//
// Особые значения, чтобы вызывать каждое состояние руками:
//  - текущий пароль, начинающийся с wrong, отвечает invalid_credentials;
//  - новый пароль слабее политики (password..., qwerty..., короче минимума) отвечает password_policy;
//  - адрес limited@example.org при смене почты отвечает rate_limited;
//  - имя, состоящее из пробелов, отвечает 422 у поля name.

const WEAK_PASSWORD = /^(password|qwerty|12345)/i;

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const unauth = () => demoError(401, "auth_required", "Authentication required");

const initialsOf = (name: string): string =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");

const invalid = (field: string, code: string, msg: string) =>
  ({
    status: 422,
    data: { detail: [{ loc: ["body", field], code, msg }] },
  }) satisfies DemoResponse;

export const createAccountRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  {
    method: "GET",
    pattern: "/account",
    handler: () => {
      const account = accountOf(getWorld());
      return account ? demoJson(account.profile) : unauth();
    },
  },
  {
    method: "PATCH",
    pattern: "/account",
    handler: (req) => {
      const world = getWorld();
      const account = accountOf(world);
      if (!account || !world.bootstrap.user) return unauth();
      const body = (req.body ?? {}) as Record<string, unknown>;
      const next = { ...account.profile };

      if (typeof body.name === "string") {
        const name = body.name.replace(/\s+/g, " ").trim();
        if (name === "") return invalid("name", "required", "Укажи имя.");
        next.name = name;
      }
      if (typeof body.commit_name === "string") {
        const value = body.commit_name.trim();
        if (/[<>]/.test(value)) {
          return invalid(
            "commit_name",
            "name_invalid",
            "В имени нельзя использовать < и >.",
          );
        }
        next.commit_name = value === "" ? null : value;
      }
      if (typeof body.commit_email === "string") {
        const value = body.commit_email.trim();
        if (value !== "" && validateEmail(value) !== null) {
          return invalid(
            "commit_email",
            "email_invalid",
            "Это не похоже на адрес почты.",
          );
        }
        next.commit_email = value === "" ? null : value;
      }
      if (typeof body.commit_use_account_email === "boolean") {
        next.commit_use_account_email = body.commit_use_account_email;
      }
      account.profile = { ...next, ...effectiveOf(next) };
      if (next.name !== world.bootstrap.user.name) {
        world.bootstrap = {
          ...world.bootstrap,
          user: {
            ...world.bootstrap.user,
            name: next.name,
            avatar_initials: initialsOf(next.name),
          },
        };
      }
      return demoJson(account.profile);
    },
  },
  {
    method: "POST",
    pattern: "/account/password",
    handler: (req) => {
      const world = getWorld();
      const account = accountOf(world);
      if (!account) return unauth();
      const body = (req.body ?? {}) as Record<string, unknown>;
      if (str(body.current_password).startsWith("wrong")) {
        return demoError(
          401,
          "invalid_credentials",
          "Invalid email or password",
        );
      }
      const next = str(body.new_password);
      if (
        next.length < world.bootstrap.auth.password_min_length ||
        WEAK_PASSWORD.test(next)
      ) {
        return demoError(
          400,
          "password_policy",
          "Password does not meet the policy",
        );
      }
      if (body.sign_out_other_sessions === true) {
        account.sessions = account.sessions.filter((s) => s.current);
      }
      return demoNoContent();
    },
  },
  {
    method: "POST",
    pattern: "/account/email",
    handler: (req) => {
      const world = getWorld();
      if (!accountOf(world)) return unauth();
      const body = (req.body ?? {}) as Record<string, unknown>;
      if (str(body.password).startsWith("wrong")) {
        return demoError(
          401,
          "invalid_credentials",
          "Invalid email or password",
        );
      }
      if (str(body.email).trim().toLowerCase() === "limited@example.org") {
        return demoError(429, "rate_limited", "Too many attempts", {
          retry_after: 20,
        });
      }
      return demoJson({
        status: "check_email",
        link: world.bootstrap.auth.smtp_enabled
          ? null
          : `${window.location.origin}/confirm-email/ce_demo_9Lw2Qp7X`,
      });
    },
  },
  {
    method: "GET",
    pattern: "/account/sessions",
    handler: () => {
      const account = accountOf(getWorld());
      return account ? demoJson(account.sessions) : unauth();
    },
  },
  {
    method: "DELETE",
    pattern: "/account/sessions",
    handler: () => {
      const account = accountOf(getWorld());
      if (!account) return unauth();
      account.sessions = account.sessions.filter((s) => s.current);
      return demoNoContent();
    },
  },
  {
    method: "DELETE",
    pattern: "/account/sessions/:id",
    handler: (req) => {
      const world = getWorld();
      const account = accountOf(world);
      if (!account) return unauth();
      const target = account.sessions.find((s) => s.id === req.params.id);
      if (!target) return demoError(404, "not_found", "Not Found");
      if (target.current) {
        signOut(world);
        return demoNoContent();
      }
      account.sessions = account.sessions.filter((s) => s.id !== target.id);
      return demoNoContent();
    },
  },
];
