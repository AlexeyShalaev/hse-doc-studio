import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import type { AccountPasskeyList } from "@entities/session";
import { identityRows } from "./lib/identityRows";
import { PasskeysCard } from "./ui/PasskeysCard";
import { ReauthDialog } from "./ui/ReauthDialog";
import type * as WebAuthnModule from "@shared/lib/webauthn";
import type * as AccountApiModule from "./api/accountApi";

const webauthn = vi.hoisted(() => ({
  createPasskey: vi.fn(),
  getPasskey: vi.fn(),
}));
vi.mock("@shared/lib/webauthn", async (original) => ({
  ...(await original<typeof WebAuthnModule>()),
  createPasskey: webauthn.createPasskey,
  getPasskey: webauthn.getPasskey,
}));

const api = vi.hoisted(() => ({
  passkeyOptions: vi.fn(),
  createPasskey: vi.fn(),
  deletePasskey: vi.fn(),
  renamePasskey: vi.fn(),
  reauth: vi.fn(),
  reauthOptions: vi.fn(),
}));
vi.mock("./api/accountApi", async (original) => {
  const real = await original<typeof AccountApiModule>();
  return { ...real, accountApi: { ...real.accountApi, ...api } };
});

const { PasskeyCeremonyError } = await import("@shared/lib/webauthn");
const { usePasskeys } = await import("./model/usePasskeys");

const LIST: AccountPasskeyList = {
  items: [
    {
      id: "pk1",
      name: "MacBook Анны",
      created_at: "2026-11-01T09:30:00Z",
      last_used_at: "2026-11-03T08:05:00Z",
      synced: true,
      domain: "studio.example.org",
      domain_matches: true,
    },
    {
      id: "pk2",
      name: "YubiKey 5",
      created_at: "2026-10-20T14:00:00Z",
      last_used_at: null,
      synced: false,
      domain: "old-studio.example.org",
      domain_matches: false,
    },
  ],
  enabled: true,
  domain: "studio.example.org",
  has_password: true,
  limit: 20,
};

const reauthRequired = () =>
  new ApiError("confirm", "reauth_required", 403, null);

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  vi.clearAllMocks();
});
afterEach(cleanup);

describe("карточка passkey", () => {
  const mount = (props: Partial<Parameters<typeof PasskeysCard>[0]> = {}) => {
    const handlers = { onAdd: vi.fn(), onRename: vi.fn(), onDelete: vi.fn() };
    render(
      <PasskeysCard
        status="ready"
        data={LIST}
        browserSupported
        {...handlers}
        {...props}
      />,
    );
    return handlers;
  };

  it("показывает синхронизацию и ключ чужого адреса", () => {
    mount();
    const own = screen.getByTestId("passkey-item-pk1");
    expect(within(own).getByText("синхронизируется")).toBeInTheDocument();
    const other = screen.getByTestId("passkey-item-pk2");
    expect(
      within(other).getByText(/привязан к old-studio\.example\.org/),
    ).toBeInTheDocument();
    expect(within(other).getByText(/ещё не использовался/)).toBeInTheDocument();
  });

  it("кнопка добавления выключена, если passkey выключены или браузер не умеет", () => {
    const { unmount } = render(
      <PasskeysCard
        status="ready"
        data={{ ...LIST, enabled: false }}
        browserSupported
        onAdd={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByTestId("passkey-add")).toBeDisabled();
    expect(screen.getByTestId("passkeys-blocked")).toBeInTheDocument();
    unmount();
    mount({ browserSupported: false });
    expect(screen.getByTestId("passkey-add")).toBeDisabled();
  });

  it("на пределе ключей добавить нельзя", () => {
    mount({ data: { ...LIST, limit: 2 } });
    expect(screen.getByTestId("passkey-add")).toBeDisabled();
    expect(screen.getByTestId("passkeys-blocked")).toHaveTextContent("2");
  });

  it("удаление просит подтверждения", async () => {
    const user = userEvent.setup();
    const { onDelete } = mount();
    await user.click(screen.getByTestId("passkey-delete-pk2"));
    expect(onDelete).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("passkey-delete-confirm"));
    expect(onDelete).toHaveBeenCalledWith("pk2");
  });

  it("переименование отправляет новое имя", async () => {
    const user = userEvent.setup();
    const { onRename } = mount();
    await user.click(screen.getByTestId("passkey-rename-pk1"));
    const input = screen.getByTestId("passkey-rename-input");
    await user.clear(input);
    await user.type(input, "Рабочий ноутбук");
    await user.click(screen.getByTestId("passkey-rename-save"));
    expect(onRename).toHaveBeenCalledWith("pk1", "Рабочий ноутбук");
  });

  it("последний способ входа объясняется текстом", () => {
    mount({ failure: { code: "last_login_method" } });
    expect(screen.getByTestId("passkeys-failure")).toHaveTextContent(
      "Это единственный способ входа.",
    );
  });
});

describe("подтверждение личности", () => {
  const props = {
    open: true,
    providers: [{ id: "hse", label: "HSE ID" }],
    onPassword: vi.fn(),
    onPasskey: vi.fn(),
    onCancel: vi.fn(),
  };

  it("пароль уходит в onPassword", async () => {
    const user = userEvent.setup();
    render(<ReauthDialog {...props} hasPassword hasPasskey={false} />);
    expect(screen.queryByTestId("reauth-passkey")).toBeNull();
    await user.type(screen.getByTestId("reauth-password"), "secret pass");
    await user.click(screen.getByTestId("reauth-submit"));
    expect(props.onPassword).toHaveBeenCalledWith("secret pass");
  });

  it("passkey без пароля: только кнопка ключа", async () => {
    const user = userEvent.setup();
    render(<ReauthDialog {...props} hasPassword={false} hasPasskey />);
    expect(screen.queryByTestId("reauth-password")).toBeNull();
    await user.click(screen.getByTestId("reauth-passkey"));
    expect(props.onPasskey).toHaveBeenCalled();
  });

  it("только единый вход: ссылка на новый вход через провайдера", () => {
    render(<ReauthDialog {...props} hasPassword={false} hasPasskey={false} />);
    const link = screen.getByTestId("reauth-sso-hse");
    expect(link.getAttribute("href")).toContain("/api/v1/auth/oidc/hse/start");
    expect(link.getAttribute("href")).toContain(
      encodeURIComponent("/settings/account"),
    );
  });
});

describe("действия с passkey", () => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={new QueryClient()}>
      {children}
    </QueryClientProvider>
  );

  it("после reauth_required открывает подтверждение и повторяет добавление", async () => {
    api.passkeyOptions
      .mockRejectedValueOnce(reauthRequired())
      .mockResolvedValueOnce({ options: { challenge: "c" } });
    api.reauth.mockResolvedValue({ reauth_until: "2026-11-03T12:10:00Z" });
    webauthn.createPasskey.mockResolvedValue({ id: "new" });
    api.createPasskey.mockResolvedValue(LIST.items[0]);
    const { result } = renderHook(() => usePasskeys(), { wrapper });

    let adding: Promise<void> | undefined;
    act(() => {
      adding = result.current.add();
    });
    await waitFor(() => {
      expect(result.current.reauth.open).toBe(true);
    });
    await act(async () => {
      await result.current.reauth.withPassword("pw");
      await adding;
    });
    expect(api.reauth).toHaveBeenCalledWith({
      password: "pw",
      credential: null,
    });
    expect(api.passkeyOptions).toHaveBeenCalledTimes(2);
    expect(webauthn.createPasskey).toHaveBeenCalledWith({ challenge: "c" });
    expect(api.createPasskey).toHaveBeenCalledWith(
      expect.objectContaining({ credential: { id: "new" } }),
    );
    expect(result.current.failure).toBeNull();
    expect(result.current.reauth.open).toBe(false);
  });

  it("отмена подтверждения не показывает ошибку", async () => {
    api.deletePasskey.mockRejectedValue(reauthRequired());
    const { result } = renderHook(() => usePasskeys(), { wrapper });
    let removing: Promise<void> | undefined;
    act(() => {
      removing = result.current.remove("pk1");
    });
    await waitFor(() => {
      expect(result.current.reauth.open).toBe(true);
    });
    await act(async () => {
      result.current.reauth.cancel();
      await removing;
    });
    expect(result.current.failure).toBeNull();
    expect(api.deletePasskey).toHaveBeenCalledTimes(1);
  });

  it("последний способ входа приходит отказом карточки", async () => {
    api.deletePasskey.mockRejectedValue(
      new ApiError("last", "last_login_method", 409, null),
    );
    const { result } = renderHook(() => usePasskeys(), { wrapper });
    await act(async () => {
      await result.current.remove("pk1");
    });
    expect(result.current.failure).toEqual({ code: "last_login_method" });
  });

  it("ключ уже на устройстве и отмена окна различаются", async () => {
    api.passkeyOptions.mockResolvedValue({ options: {} });
    webauthn.createPasskey.mockRejectedValueOnce(
      new PasskeyCeremonyError("already_registered"),
    );
    const { result } = renderHook(() => usePasskeys(), { wrapper });
    await act(async () => {
      await result.current.add();
    });
    expect(result.current.failure).toEqual({
      code: "passkey_already_registered",
    });
    webauthn.createPasskey.mockRejectedValueOnce(
      new PasskeyCeremonyError("cancelled"),
    );
    await act(async () => {
      await result.current.add();
    });
    expect(result.current.failure).toBeNull();
  });

  it("неверный пароль в подтверждении оставляет окно открытым", async () => {
    api.deletePasskey.mockRejectedValueOnce(reauthRequired());
    api.reauth.mockRejectedValueOnce(
      new ApiError("bad", "invalid_credentials", 401, null),
    );
    const { result } = renderHook(() => usePasskeys(), { wrapper });
    act(() => {
      void result.current.remove("pk1");
    });
    await waitFor(() => {
      expect(result.current.reauth.open).toBe(true);
    });
    await act(async () => {
      await result.current.reauth.withPassword("wrong");
    });
    expect(result.current.reauth.open).toBe(true);
    expect(result.current.reauth.failure).toEqual({
      code: "invalid_credentials",
    });
  });
});

describe("способы входа с passkey", () => {
  it("рабочий passkey позволяет отвязать единственный SSO", () => {
    const linked = [
      {
        provider: "hse",
        label: "HSE ID",
        email: "anna@example.org",
        email_verified: true,
      },
    ];
    expect(identityRows(linked, false, null)[0]?.can_unlink).toBe(false);
    expect(identityRows(linked, false, null, true)[0]?.can_unlink).toBe(true);
  });
});
