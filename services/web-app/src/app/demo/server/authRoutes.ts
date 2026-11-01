import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type { ServerDemoWorld } from "./world";

// Демо регистрации, приглашений, подтверждения почты и сброса пароля. Тело ответов
// совпадает с contracts/server/fixtures (RegisterResponse, ForgotResponse, InvitationInfo).
//
// Особые значения, чтобы вызывать каждое состояние руками:
//  - адрес limited@example.org: отказ rate_limited;
//  - адрес approval@example.org: регистрация ждёт одобрения;
//  - любой токен со словом expired или invalid: просрочен или неверен;
//  - токен приглашения inv_plain: приглашение без организации;
//  - в режиме domains почта принимается только на example.org, hse.ru и edu.hse.ru.

export const DEMO_ALLOWED_DOMAINS = ["example.org", "hse.ru", "edu.hse.ru"];
export const DEMO_INVITED_EMAIL = "maria.keller@example.org";

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const badToken = (token: string): boolean =>
  token === "" || /expired|invalid/i.test(token);

const origin = (): string =>
  typeof window === "undefined"
    ? "https://studio.example.org"
    : window.location.origin;

const linkTo = (kind: "verify" | "reset", token: string): string =>
  `${origin()}/${kind}/${token}`;

const WEAK_PASSWORD = /^(password|qwerty|12345)/i;

const limited = (email: string) =>
  email.trim().toLowerCase() === "limited@example.org"
    ? demoError(429, "rate_limited", "Too many attempts", { retry_after: 20 })
    : null;

export const createAuthRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  {
    method: "POST",
    pattern: "/auth/register",
    handler: (req) => {
      const { auth } = getWorld().bootstrap;
      const body = (req.body ?? {}) as Record<string, unknown>;
      const email = str(body.email).trim().toLowerCase();
      const token =
        typeof body.invitation_token === "string"
          ? body.invitation_token
          : null;
      const rate = limited(email);
      if (rate) return rate;

      if (token !== null) {
        if (badToken(token)) {
          return demoError(
            400,
            "invitation_invalid",
            "Invitation is invalid or expired",
          );
        }
      } else {
        if (!auth.password_enabled || auth.registration_mode === "closed") {
          return demoError(
            403,
            "registration_closed",
            "Registration is closed",
          );
        }
        if (auth.registration_mode === "invite") {
          return demoError(
            403,
            "invitation_required",
            "Invitation is required",
          );
        }
        // Открытая регистрация без SMTP не подтвердит почту и ссылку анониму не покажет: нужно приглашение.
        if (auth.registration_mode === "open" && !auth.smtp_enabled) {
          return demoError(
            403,
            "invitation_required",
            "Invitation is required",
          );
        }
        const domain = email.split("@")[1] ?? "";
        if (
          auth.registration_mode === "domains" &&
          !DEMO_ALLOWED_DOMAINS.includes(domain)
        ) {
          return demoError(
            403,
            "domain_not_allowed",
            "Email domain is not allowed",
          );
        }
      }
      const password = str(body.password);
      if (
        password.length < auth.password_min_length ||
        WEAK_PASSWORD.test(password)
      ) {
        return demoError(
          400,
          "password_policy",
          "Password does not meet the policy",
        );
      }
      // Ответ нейтральный: занятый адрес (taken@) отвечает так же, как свободный.
      const approval =
        email.startsWith("approval@") ||
        (auth.registration_mode === "domains" && !auth.smtp_enabled);
      return demoJson({
        status: approval ? "pending_approval" : "check_email",
        link:
          !approval && !auth.smtp_enabled
            ? linkTo("verify", "vf_demo_3Hn8Zc1Q")
            : null,
      });
    },
  },
  {
    method: "GET",
    pattern: "/auth/invitations/:token",
    handler: (req) => {
      const token = req.params.token ?? "";
      if (badToken(token)) {
        return demoError(
          400,
          "invitation_invalid",
          "Invitation is invalid or expired",
        );
      }
      return demoJson({
        email: DEMO_INVITED_EMAIL,
        invited_by: "Иван Сидоров",
        org_name: token === "inv_plain" ? null : "МСПИН 2025",
      });
    },
  },
  {
    method: "POST",
    pattern: "/auth/verify",
    handler: (req) => {
      const body = (req.body ?? {}) as Record<string, unknown>;
      if (badToken(str(body.token))) {
        return demoError(400, "token_invalid", "Link is invalid or expired");
      }
      return demoNoContent();
    },
  },
  {
    method: "POST",
    pattern: "/auth/verify/resend",
    handler: (req) => {
      const body = (req.body ?? {}) as Record<string, unknown>;
      const rate = limited(str(body.email));
      if (rate) return rate;
      // Как на сервере: ссылку не отдаём ни с SMTP, ни без (не раскрываем, есть ли аккаунт).
      return demoJson({ status: "check_email", link: null });
    },
  },
  {
    method: "POST",
    pattern: "/auth/forgot",
    handler: (req) => {
      const body = (req.body ?? {}) as Record<string, unknown>;
      const rate = limited(str(body.email));
      if (rate) return rate;
      // Ответ не зависит от того, есть ли такой аккаунт; ссылку, как и сервер, не отдаём.
      return demoJson({ status: "check_email", link: null });
    },
  },
  {
    method: "POST",
    pattern: "/auth/reset",
    handler: (req) => {
      const { auth } = getWorld().bootstrap;
      const body = (req.body ?? {}) as Record<string, unknown>;
      if (badToken(str(body.token))) {
        return demoError(400, "token_invalid", "Link is invalid or expired");
      }
      const password = str(body.password);
      if (
        password.length < auth.password_min_length ||
        WEAK_PASSWORD.test(password)
      ) {
        return demoError(
          400,
          "password_policy",
          "Password does not meet the policy",
        );
      }
      return demoNoContent();
    },
  },
];
