import { MemoryRouter } from "react-router";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import type { AuthOptions } from "@entities/session";
import { AUTH_ERROR_CODES } from "../lib/authErrorCodes";
import type { LoginFailure } from "../lib/loginErrors";
import { AuthErrorCard } from "./AuthErrorCard";
import { LoginCard } from "./LoginCard";
import { SignInForm } from "./SignInForm";

const PASSWORD: AuthOptions = {
  registration_mode: "domains",
  password_enabled: true,
  oidc_providers: [],
  smtp_enabled: true,
  password_min_length: 10,
};
const WITH_SSO: AuthOptions = {
  ...PASSWORD,
  oidc_providers: [
    { id: "hse", label: "HSE ID" },
    { id: "google", label: "Google" },
  ],
};
const SSO_ONLY: AuthOptions = {
  ...WITH_SSO,
  password_enabled: false,
  registration_mode: "closed",
};

const card = (
  auth: AuthOptions,
  failure: LoginFailure | null = null,
  pending = false,
  initialEmail = "",
) => (
  <MemoryRouter>
    <LoginCard
      auth={auth}
      failure={failure}
      pending={pending}
      initialEmail={initialEmail}
      ssoHref={(id) => `#sso-${id}`}
      onSubmit={() => undefined}
    />
  </MemoryRouter>
);

const failureEntry = (code: string, title: string, note: string) => ({
  id: `login_error_${code}`,
  title,
  note,
  frame: "window" as const,
  width: 460,
  render: () => card(PASSWORD, { code }, false, "anna.petrova@example.org"),
});

/** Состояния входа и экрана /auth/error для галереи серверных экранов. */
export const getSignInGallery = (): GalleryGroup[] => [
  {
    id: "login-states",
    title: "Вход: форма",
    description: "Основные виды экрана входа.",
    entries: [
      {
        id: "login_password",
        title: "Только пароль",
        frame: "window",
        width: 460,
        render: () => card(PASSWORD),
      },
      {
        id: "login_password_sso",
        title: "Пароль и SSO",
        note: "Кнопки провайдеров под разделителем.",
        frame: "window",
        width: 460,
        render: () => card(WITH_SSO),
      },
      {
        id: "login_sso_only",
        title: "Только SSO",
        note: "Формы пароля нет, регистрации нет.",
        frame: "window",
        width: 460,
        render: () => card(SSO_ONLY),
      },
      {
        id: "login_no_methods",
        title: "Нет способов входа",
        frame: "window",
        width: 460,
        render: () =>
          card({
            ...PASSWORD,
            password_enabled: false,
            registration_mode: "closed",
          }),
      },
      {
        id: "login_submitting",
        title: "Идёт вход",
        frame: "window",
        width: 460,
        render: () => card(PASSWORD, null, true, "anna.petrova@example.org"),
      },
    ],
  },
  {
    id: "login-errors",
    title: "Вход: отказы по кодам",
    description:
      "Каждый код из contracts/server/error_codes.json со своим текстом.",
    entries: [
      failureEntry(
        "invalid_credentials",
        "Неверные данные",
        "Без подсказки, какое из полей неверно.",
      ),
      failureEntry(
        "email_not_verified",
        "Почта не подтверждена",
        "Мягкий тон.",
      ),
      failureEntry("pending_approval", "Ждёт одобрения", "Мягкий тон."),
      failureEntry("account_disabled", "Аккаунт отключён", "Красный тон."),
      failureEntry(
        "sso_login_required",
        "Нужен SSO",
        "Для этой почты пароль не работает.",
      ),
      {
        id: "login_error_rate_limited",
        title: "Слишком много попыток",
        note: "Обратный отсчёт, кнопка заблокирована до нуля.",
        frame: "window",
        width: 460,
        render: () =>
          card(
            PASSWORD,
            { code: "rate_limited", retryAfter: 45 },
            false,
            "anna.petrova@example.org",
          ),
      },
      failureEntry(
        "csrf_failed",
        "Сессия устарела",
        "Страница обновилась, повторите.",
      ),
      failureEntry("network", "Нет связи", "Сервер не ответил."),
      failureEntry("unknown", "Прочая ошибка", "Неизвестный код."),
    ],
  },
  {
    id: "login-live",
    title: "Вход: живой",
    description:
      "На демо-мире. Адреса: locked@example.org (лимит), unverified@, pending@, disabled@, sso@, любой другой с паролем от 10 символов входит.",
    entries: [
      {
        id: "login_live_password",
        title: "Живая форма",
        scenario: "registration_closed",
        frame: "window",
        width: 460,
        render: () => <SignInForm />,
      },
    ],
  },
  {
    id: "auth-error",
    title: "Внешний вход не удался (/auth/error)",
    entries: [...AUTH_ERROR_CODES, "unknown" as const].map((code) => ({
      id: `auth_error_${code}`,
      title: code,
      frame: "window" as const,
      width: 460,
      render: () => (
        <MemoryRouter>
          <AuthErrorCard code={code} />
        </MemoryRouter>
      ),
    })),
  },
];
