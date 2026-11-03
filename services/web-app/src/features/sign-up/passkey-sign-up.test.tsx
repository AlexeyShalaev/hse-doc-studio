import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import type { AuthOptions, InvitationInfo } from "@entities/session";
import type * as WebAuthnModule from "@shared/lib/webauthn";
import type * as SignUpApiModule from "./api/signUpApi";
import type * as SessionModule from "@entities/session";
import type * as SharedApiModule from "@shared/api";

const webauthn = vi.hoisted(() => ({
  supportsPasskeys: vi.fn(() => true),
  createPasskey: vi.fn(),
}));
vi.mock("@shared/lib/webauthn", async (original) => ({
  ...(await original<typeof WebAuthnModule>()),
  ...webauthn,
}));

const api = vi.hoisted(() => ({
  passkeyOptions: vi.fn(),
  passkeyRegister: vi.fn(),
  invitation: vi.fn(),
}));
vi.mock("./api/signUpApi", async (original) => {
  const real = await original<typeof SignUpApiModule>();
  return { ...real, signUpApi: { ...real.signUpApi, ...api } };
});

const AUTH: AuthOptions = {
  registration_mode: "invite",
  password_enabled: true,
  oidc_providers: [],
  smtp_enabled: true,
  password_min_length: 10,
  passkeys_enabled: true,
};

const session = vi.hoisted(() => ({
  refresh: vi.fn(),
  auth: null as AuthOptions | null,
}));
vi.mock("@entities/session", async (original) => ({
  ...(await original<typeof SessionModule>()),
  useRefreshSession: () => session.refresh,
  clearUserScopedCache: vi.fn(() => Promise.resolve()),
  useBootstrap: () => ({ data: { auth: session.auth } }),
}));

const csrf = vi.hoisted(() => ({ set: vi.fn() }));
vi.mock("@shared/api", async (original) => ({
  ...(await original<typeof SharedApiModule>()),
  setCsrfToken: csrf.set,
}));

const { PasskeyCeremonyError } = await import("@shared/lib/webauthn");
const { usePasskeySignUp } = await import("./model/usePasskeySignUp");
const { RegisterCard } = await import("./ui/RegisterCard");
const { InviteForm } = await import("./ui/InviteForm");

const INVITATION: InvitationInfo = {
  email: "maria.keller@example.org",
  invited_by: "Иван Сидоров",
  org_name: null,
};

const LOGIN = {
  user: {
    id: "u1",
    name: "Мария",
    email: "maria.keller@example.org",
    avatar_initials: "М",
    is_instance_admin: false,
    email_verified: true,
    locale: "ru",
    org_roles: [],
  },
  csrf_token: "csrf-1",
};

const wrapper = ({ children }: { children: ReactNode }) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/invite/tok"]}>
        <Routes>
          <Route path="/invite/:token" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  vi.clearAllMocks();
  webauthn.supportsPasskeys.mockReturnValue(true);
  session.auth = AUTH;
});
afterEach(cleanup);

describe("регистрация по приглашению с passkey: карточка", () => {
  const card = (props: Partial<Parameters<typeof RegisterCard>[0]>) =>
    render(
      <RegisterCard
        auth={AUTH}
        invitation={INVITATION}
        onSubmit={() => undefined}
        {...props}
      />,
      { wrapper },
    );

  it("без passkey кнопки нет, форма пароля как раньше", () => {
    card({});
    expect(screen.queryByTestId("register-passkey")).toBeNull();
    expect(screen.getByLabelText("Пароль")).toBeTruthy();
  });

  it("кнопка ждёт имя и передаёт его", () => {
    const onStart = vi.fn();
    card({ passkey: { available: true, pending: false, onStart } });
    const button = screen.getByTestId<HTMLButtonElement>("register-passkey");
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Имя"), {
      target: { value: " Мария Келлер " },
    });
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    expect(onStart).toHaveBeenCalledWith("Мария Келлер");
    // Пароль остаётся запасным путём.
    expect(screen.getByLabelText("Пароль")).toBeTruthy();
  });

  it("без входа по паролю полей пароля нет, только passkey", () => {
    card({
      auth: { ...AUTH, password_enabled: false },
      passkey: { available: true, pending: false, onStart: vi.fn() },
    });
    expect(screen.getByTestId("register-passkey")).toBeTruthy();
    expect(screen.queryByLabelText("Пароль")).toBeNull();
    expect(screen.queryByTestId("register-form")).toBeTruthy();
  });

  it("отказ email_taken показывается над формой своим текстом", () => {
    card({
      failure: { code: "email_taken" },
      passkey: { available: true, pending: false, onStart: vi.fn() },
    });
    expect(screen.getByTestId("register-error").textContent).toContain(
      "У этого адреса уже есть аккаунт",
    );
  });
});

describe("регистрация по приглашению с passkey: страница", () => {
  it("кнопка только для приглашения на адрес и при включённом passkey", async () => {
    api.invitation.mockResolvedValue(INVITATION);
    const { unmount } = render(<InviteForm token="tok" />, { wrapper });
    expect(await screen.findByTestId("register-passkey")).toBeTruthy();
    unmount();

    api.invitation.mockResolvedValue({ ...INVITATION, email: "" });
    const second = render(<InviteForm token="tok" />, { wrapper });
    expect(await screen.findByTestId("register-form")).toBeTruthy();
    expect(screen.queryByTestId("register-passkey")).toBeNull();
    second.unmount();

    session.auth = { ...AUTH, passkeys_enabled: false };
    api.invitation.mockResolvedValue(INVITATION);
    render(<InviteForm token="tok" />, { wrapper });
    expect(await screen.findByTestId("register-form")).toBeTruthy();
    expect(screen.queryByTestId("register-passkey")).toBeNull();
  });

  it("без пароля и без passkey регистрация закрыта", async () => {
    session.auth = {
      ...AUTH,
      password_enabled: false,
      passkeys_enabled: false,
    };
    api.invitation.mockResolvedValue(INVITATION);
    render(<InviteForm token="tok" />, { wrapper });
    expect(await screen.findByText("Регистрация закрыта")).toBeTruthy();
  });

  it("без пароля, но с passkey: форма с кнопкой passkey", async () => {
    session.auth = { ...AUTH, password_enabled: false };
    api.invitation.mockResolvedValue(INVITATION);
    render(<InviteForm token="tok" />, { wrapper });
    expect(await screen.findByTestId("register-passkey")).toBeTruthy();
    expect(screen.queryByLabelText("Пароль")).toBeNull();
  });
});

describe("usePasskeySignUp", () => {
  it("вызов, ключ и вход как у пароля, имя ключа по устройству", async () => {
    api.passkeyOptions.mockResolvedValue({ options: { challenge: "c" } });
    webauthn.createPasskey.mockResolvedValue({ id: "cred" });
    api.passkeyRegister.mockResolvedValue(LOGIN);
    const { result } = renderHook(
      () => usePasskeySignUp("tok", { enabled: true }),
      { wrapper },
    );
    expect(result.current.available).toBe(true);

    await act(async () => {
      await result.current.start("Мария");
    });

    expect(api.passkeyOptions).toHaveBeenCalledWith({
      invitation_token: "tok",
      name: "Мария",
    });
    expect(webauthn.createPasskey).toHaveBeenCalledWith({ challenge: "c" });
    const body = api.passkeyRegister.mock.calls[0]?.[0] as {
      passkey_name: string | null;
      credential: unknown;
    };
    expect(body.credential).toEqual({ id: "cred" });
    expect(body.passkey_name === null || body.passkey_name.length > 0).toBe(
      true,
    );
    expect(csrf.set).toHaveBeenCalledWith("csrf-1");
    expect(session.refresh).toHaveBeenCalled();
    expect(result.current.failure).toBeNull();
  });

  it("адрес уже занят: код email_taken, вход не открывается", async () => {
    api.passkeyOptions.mockRejectedValue(
      new ApiError("taken", "email_taken", 409),
    );
    const { result } = renderHook(
      () => usePasskeySignUp("tok", { enabled: true }),
      { wrapper },
    );
    await act(async () => {
      await result.current.start("Мария");
    });
    expect(result.current.failure?.code).toBe("email_taken");
    expect(webauthn.createPasskey).not.toHaveBeenCalled();
    expect(csrf.set).not.toHaveBeenCalled();
  });

  it("закрытое окно создания ключа молчит, сбой браузера показывается", async () => {
    api.passkeyOptions.mockResolvedValue({ options: { challenge: "c" } });
    webauthn.createPasskey.mockRejectedValue(
      new PasskeyCeremonyError("cancelled"),
    );
    const { result } = renderHook(
      () => usePasskeySignUp("tok", { enabled: true }),
      { wrapper },
    );
    await act(async () => {
      await result.current.start("Мария");
    });
    expect(result.current.failure).toBeNull();
    expect(api.passkeyRegister).not.toHaveBeenCalled();

    webauthn.createPasskey.mockRejectedValue(
      new PasskeyCeremonyError("failed"),
    );
    await act(async () => {
      await result.current.start("Мария");
    });
    expect(result.current.failure?.code).toBe("passkey_failed");
  });

  it("без поддержки в браузере недоступно", () => {
    webauthn.supportsPasskeys.mockReturnValue(false);
    const { result } = renderHook(
      () => usePasskeySignUp("tok", { enabled: true }),
      { wrapper },
    );
    expect(result.current.available).toBe(false);
  });
});
