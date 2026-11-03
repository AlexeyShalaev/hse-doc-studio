import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import type { AuthOptions } from "@entities/session";
import { LoginCard } from "./ui/LoginCard";
import { loginErrorKey } from "./lib/loginErrors";
import type * as WebAuthnModule from "@shared/lib/webauthn";
import type * as SignInApiModule from "./api/signInApi";
import type * as SessionModule from "@entities/session";

const webauthn = vi.hoisted(() => ({
  supportsPasskeys: vi.fn(() => true),
  supportsAutofill: vi.fn(() => Promise.resolve(false)),
  getPasskey: vi.fn(),
  cancelPasskeyCeremony: vi.fn(() => Promise.resolve()),
}));
vi.mock("@shared/lib/webauthn", async (original) => ({
  ...(await original<typeof WebAuthnModule>()),
  ...webauthn,
}));

const api = vi.hoisted(() => ({
  passkeyOptions: vi.fn(),
  passkeyLogin: vi.fn(),
}));
vi.mock("./api/signInApi", async (original) => {
  const real = await original<typeof SignInApiModule>();
  return { ...real, signInApi: { ...real.signInApi, ...api } };
});

const session = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("@entities/session", async (original) => ({
  ...(await original<typeof SessionModule>()),
  useRefreshSession: () => session.refresh,
  clearUserScopedCache: vi.fn(() => Promise.resolve()),
}));

const { PasskeyCeremonyError } = await import("@shared/lib/webauthn");
const { usePasskeySignIn } = await import("./model/usePasskeySignIn");

const AUTH: AuthOptions = {
  registration_mode: "invite",
  password_enabled: true,
  oidc_providers: [],
  smtp_enabled: true,
  password_min_length: 10,
  passkeys_enabled: true,
};

const LOGIN = {
  user: {
    id: "u1",
    name: "Анна",
    email: "anna@example.org",
    avatar_initials: "А",
    is_instance_admin: false,
    email_verified: true,
    locale: "ru",
    org_roles: [],
  },
  csrf_token: "csrf-1",
};

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>
    {children}
  </QueryClientProvider>
);

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  vi.clearAllMocks();
  webauthn.supportsPasskeys.mockReturnValue(true);
  webauthn.supportsAutofill.mockResolvedValue(false);
});
afterEach(cleanup);

describe("кнопка passkey на экране входа", () => {
  const renderCard = (props: Partial<Parameters<typeof LoginCard>[0]>) =>
    render(
      <MemoryRouter>
        <LoginCard
          auth={AUTH}
          ssoHref={(id) => `#${id}`}
          onSubmit={() => undefined}
          {...props}
        />
      </MemoryRouter>,
    );

  it("без passkey кнопки нет, поле почты без webauthn", () => {
    renderCard({});
    expect(screen.queryByTestId("login-passkey")).toBeNull();
    expect(screen.getByLabelText("Почта")).toHaveAttribute(
      "autocomplete",
      "username",
    );
  });

  it("с passkey есть кнопка и подсказки автозаполнения", () => {
    const onStart = vi.fn();
    renderCard({ passkey: { available: true, pending: false, onStart } });
    fireEvent.click(screen.getByTestId("login-passkey"));
    expect(onStart).toHaveBeenCalled();
    expect(screen.getByLabelText("Почта")).toHaveAttribute(
      "autocomplete",
      "username webauthn",
    );
  });

  it("без пароля кнопка passkey остаётся, «нет способов входа» не показывается", () => {
    renderCard({
      auth: { ...AUTH, password_enabled: false },
      passkey: { available: true, pending: false, onStart: vi.fn() },
    });
    expect(screen.getByTestId("login-passkey")).toBeInTheDocument();
    expect(screen.queryByTestId("login-no-methods")).toBeNull();
  });

  it("тексты отказов passkey есть на обоих языках", async () => {
    for (const lng of ["ru", "en"]) {
      await i18n.changeLanguage(lng);
      for (const code of [
        "passkey_invalid",
        "passkeys_disabled",
        "passkey_failed",
      ]) {
        expect(i18n.exists(`auth:${loginErrorKey(code)}`), code).toBe(true);
      }
    }
  });
});

describe("вход по passkey", () => {
  it("кнопка: вызов, ключ и вход как у пароля", async () => {
    api.passkeyOptions.mockResolvedValue({ options: { challenge: "c" } });
    webauthn.getPasskey.mockResolvedValue({ id: "cred" });
    api.passkeyLogin.mockResolvedValue(LOGIN);
    const { result } = renderHook(() => usePasskeySignIn(true), { wrapper });
    expect(result.current.available).toBe(true);
    await act(async () => {
      await result.current.start();
    });
    expect(webauthn.getPasskey).toHaveBeenCalledWith({ challenge: "c" });
    expect(api.passkeyLogin).toHaveBeenCalledWith({ id: "cred" });
    expect(session.refresh).toHaveBeenCalled();
    expect(result.current.failure).toBeNull();
  });

  it("отказ сервера показывается, отмена окна молчит", async () => {
    api.passkeyOptions.mockResolvedValue({ options: {} });
    webauthn.getPasskey.mockResolvedValueOnce({ id: "cred" });
    api.passkeyLogin.mockRejectedValueOnce(
      new ApiError("bad", "passkey_invalid", 401, null),
    );
    const { result } = renderHook(() => usePasskeySignIn(true), { wrapper });
    await act(async () => {
      await result.current.start();
    });
    expect(result.current.failure).toEqual({ code: "passkey_invalid" });
    webauthn.getPasskey.mockRejectedValueOnce(
      new PasskeyCeremonyError("cancelled"),
    );
    await act(async () => {
      await result.current.start();
    });
    expect(result.current.failure).toBeNull();
  });

  it("автозаполнение стартует само, если браузер умеет", async () => {
    webauthn.supportsAutofill.mockResolvedValue(true);
    api.passkeyOptions.mockResolvedValue({ options: { challenge: "a" } });
    webauthn.getPasskey.mockReturnValue(new Promise(() => undefined));
    const { unmount } = renderHook(() => usePasskeySignIn(true), { wrapper });
    await waitFor(() => {
      expect(webauthn.getPasskey).toHaveBeenCalledWith(
        { challenge: "a" },
        { autofill: true },
      );
    });
    unmount();
    expect(webauthn.cancelPasskeyCeremony).toHaveBeenCalled();
  });

  it("автозаполнение без вызова (лимит) не повторяет запрос", async () => {
    webauthn.supportsAutofill.mockResolvedValue(true);
    api.passkeyOptions.mockRejectedValue(new Error("rate limited"));
    const { result } = renderHook(() => usePasskeySignIn(true), { wrapper });
    await waitFor(() => {
      expect(api.passkeyOptions).toHaveBeenCalledTimes(1);
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.passkeyOptions).toHaveBeenCalledTimes(1);
    expect(webauthn.getPasskey).not.toHaveBeenCalled();
    expect(result.current.failure).toBeNull();
  });

  it("браузер без поддержки автозаполнения: ни ошибки, ни повторов", async () => {
    webauthn.supportsAutofill.mockResolvedValue(true);
    api.passkeyOptions.mockResolvedValue({ options: { challenge: "a" } });
    webauthn.getPasskey.mockRejectedValue(
      new PasskeyCeremonyError("unsupported"),
    );
    const { result } = renderHook(() => usePasskeySignIn(true), { wrapper });
    await waitFor(() => {
      expect(webauthn.getPasskey).toHaveBeenCalledTimes(1);
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.passkeyOptions).toHaveBeenCalledTimes(1);
    expect(result.current.failure).toBeNull();
  });

  it("отказ сервера после выбора ключа: ожидание снова, но не больше трёх раз", async () => {
    webauthn.supportsAutofill.mockResolvedValue(true);
    api.passkeyOptions.mockResolvedValue({ options: { challenge: "a" } });
    webauthn.getPasskey.mockResolvedValue({ id: "cred" });
    api.passkeyLogin.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => usePasskeySignIn(true), { wrapper });
    await waitFor(() => {
      expect(api.passkeyLogin).toHaveBeenCalledTimes(4);
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.passkeyLogin).toHaveBeenCalledTimes(4);
    expect(result.current.failure).not.toBeNull();
  });

  it("выключенный passkey ничего не запускает", () => {
    const { result } = renderHook(() => usePasskeySignIn(false), { wrapper });
    expect(result.current.available).toBe(false);
    expect(webauthn.supportsAutofill).not.toHaveBeenCalled();
  });
});
