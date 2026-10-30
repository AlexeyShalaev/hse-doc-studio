import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { AccountProfile, AccountSession } from "@entities/session";
import { patchFor, modeOf, previewOf } from "./lib/commitIdentity";
import { CommitIdentityCard } from "./ui/CommitIdentityCard";
import { PasswordCard } from "./ui/PasswordCard";
import { ProfileCard } from "./ui/ProfileCard";
import { IdentitiesCard } from "./ui/IdentitiesCard";
import { SessionsCard } from "./ui/SessionsCard";
import { TokensCard } from "./ui/TokensCard";

const PROFILE: AccountProfile = {
  id: "u_1",
  name: "Анна Петрова",
  email: "anna@example.org",
  locale: "ru",
  commit_name: null,
  commit_email: null,
  commit_use_account_email: false,
  effective_commit_name: "Анна Петрова",
  effective_commit_email: "u_1@noreply.studio.example.org",
  commit_email_is_noreply: true,
};

const SESSIONS: AccountSession[] = [
  {
    id: "cur",
    created_at: "2026-10-20T08:14:03Z",
    last_seen_at: "2026-10-27T09:41:10Z",
    ip: "203.0.113.24",
    user_agent: "Firefox на macOS",
    current: true,
  },
  {
    id: "old",
    created_at: "2026-10-12T17:02:44Z",
    last_seen_at: "2026-10-19T11:30:00Z",
    ip: null,
    user_agent: "Chrome на Windows",
    current: false,
  },
];

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});
afterEach(cleanup);

describe("сессии", () => {
  const mount = (props: Partial<Parameters<typeof SessionsCard>[0]> = {}) => {
    const onRevoke = vi.fn();
    const onRevokeOthers = vi.fn();
    render(
      <SessionsCard
        status="ready"
        sessions={SESSIONS}
        onRevoke={onRevoke}
        onRevokeOthers={onRevokeOthers}
        {...props}
      />,
    );
    return { onRevoke, onRevokeOthers };
  };

  it("текущую сессию не завершить кнопкой", () => {
    mount();
    const current = screen.getByTestId("session-cur");
    expect(within(current).getByText("Эта сессия")).toBeInTheDocument();
    expect(within(current).queryByRole("button")).toBeNull();
    expect(
      within(screen.getByTestId("session-old")).getByRole("button", {
        name: "Завершить сессию: Chrome на Windows",
      }),
    ).toBeInTheDocument();
  });

  it("«Завершить остальные» просит подтверждения и не трогает текущую", async () => {
    const user = userEvent.setup();
    const { onRevoke, onRevokeOthers } = mount();
    await user.click(screen.getByTestId("sessions-end-others"));
    expect(onRevokeOthers).not.toHaveBeenCalled();
    expect(screen.getByText("Завершить 1 другую сессию?")).toBeInTheDocument();
    await user.click(screen.getByTestId("sessions-end-others-confirm"));
    expect(onRevokeOthers).toHaveBeenCalledTimes(1);
    expect(onRevoke).not.toHaveBeenCalled();
  });

  it("отмена подтверждения возвращает кнопку", async () => {
    const user = userEvent.setup();
    const { onRevokeOthers } = mount();
    await user.click(screen.getByTestId("sessions-end-others"));
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.getByTestId("sessions-end-others")).toBeInTheDocument();
    expect(onRevokeOthers).not.toHaveBeenCalled();
  });

  it("одна сессия: завершать нечего", () => {
    mount({ sessions: SESSIONS.slice(0, 1) });
    expect(screen.getByTestId("sessions-alone")).toBeInTheDocument();
    expect(screen.queryByTestId("sessions-end-others")).toBeNull();
  });

  it("состояния загрузки и ошибки", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender } = render(
      <SessionsCard
        status="loading"
        onRevoke={vi.fn()}
        onRevokeOthers={vi.fn()}
      />,
    );
    expect(screen.getByTestId("sessions-loading")).toBeInTheDocument();
    rerender(
      <SessionsCard
        status="error"
        onRetry={onRetry}
        onRevoke={vi.fn()}
        onRevokeOthers={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe("пароль", () => {
  it("несовпадение повтора блокирует отправку", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<PasswordCard minLength={10} onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Текущий пароль"), "old password 1");
    await user.type(screen.getByLabelText("Новый пароль"), "new password 123");
    await user.type(
      screen.getByLabelText("Повторите новый пароль"),
      "other password",
    );
    await user.click(screen.getByTestId("password-submit"));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Пароли не совпадают.")).toBeInTheDocument();
  });

  it("отправляет пароли и по умолчанию закрывает остальные сессии", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<PasswordCard minLength={10} onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Текущий пароль"), "old password 1");
    await user.type(screen.getByLabelText("Новый пароль"), "new password 123");
    await user.type(
      screen.getByLabelText("Повторите новый пароль"),
      "new password 123",
    );
    await user.click(screen.getByTestId("password-submit"));
    expect(onSubmit).toHaveBeenCalledWith({
      current: "old password 1",
      next: "new password 123",
      signOutOthers: true,
    });
  });

  it("неверный текущий пароль подсвечивается у своего поля", () => {
    render(
      <PasswordCard
        minLength={10}
        failure={{ code: "invalid_credentials" }}
        onSubmit={vi.fn()}
      />,
    );
    const field = screen.getByLabelText("Текущий пароль").closest(".field");
    expect(field).toHaveTextContent("Неверный пароль.");
  });

  it("отказ сервера гаснет, когда поле правят", async () => {
    const user = userEvent.setup();
    render(
      <PasswordCard
        minLength={10}
        failure={{ code: "invalid_credentials" }}
        onSubmit={vi.fn()}
      />,
    );
    const input = screen.getByLabelText("Текущий пароль");
    expect(input.closest(".field")).toHaveTextContent("Неверный пароль.");
    await user.type(input, "x");
    expect(input.closest(".field")).not.toHaveTextContent("Неверный пароль.");
  });

  it("при входе через SSO формы нет", () => {
    render(
      <PasswordCard
        minLength={10}
        passwordEnabled={false}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("password-form")).toBeNull();
    expect(screen.getByText(/единый вход/)).toBeInTheDocument();
  });
});

describe("подпись версий", () => {
  const mount = (profile: AccountProfile = PROFILE) => {
    const onSave = vi.fn();
    render(<CommitIdentityCard profile={profile} onSave={onSave} />);
    return onSave;
  };

  it("по умолчанию скрытый адрес и пометка о приватности", () => {
    mount();
    expect(screen.getByTestId("commit-preview")).toHaveTextContent(
      "Анна Петрова <u_1@noreply.studio.example.org>",
    );
    expect(screen.getByText(/Настоящая почта не попадёт/)).toBeInTheDocument();
  });

  it("выбор настоящего адреса предупреждает, что он запишется навсегда", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByLabelText(/Почта аккаунта/));
    expect(screen.getByText(/запишется в версии навсегда/)).toBeInTheDocument();
    expect(screen.getByTestId("commit-preview")).toHaveTextContent(
      "Анна Петрова <anna@example.org>",
    );
  });

  it("свой адрес без правильной формы не отправляется", async () => {
    const user = userEvent.setup();
    const onSave = mount();
    await user.click(screen.getByLabelText(/Свой адрес/));
    await user.type(screen.getByLabelText("Адрес для версий"), "не-почта");
    await user.click(screen.getByTestId("commit-save"));
    expect(onSave).not.toHaveBeenCalled();
    expect(
      screen.getByText("Это не похоже на адрес почты."),
    ).toBeInTheDocument();
  });

  it("сохраняет выбранный режим явными полями", async () => {
    const user = userEvent.setup();
    const onSave = mount();
    await user.click(screen.getByLabelText(/Почта аккаунта/));
    await user.click(screen.getByTestId("commit-save"));
    expect(onSave).toHaveBeenCalledWith({
      commit_name: "",
      commit_email: "",
      commit_use_account_email: true,
    });
  });

  it("режим и тело запроса согласованы", () => {
    expect(modeOf(PROFILE)).toBe("noreply");
    expect(modeOf({ ...PROFILE, commit_use_account_email: true })).toBe(
      "account",
    );
    expect(modeOf({ ...PROFILE, commit_email: "a@b.co" })).toBe("own");
    expect(patchFor("own", " Anna ", " a@b.co ")).toEqual({
      commit_name: "Anna",
      commit_email: "a@b.co",
      commit_use_account_email: false,
    });
    expect(patchFor("noreply", "", "x@y.zz").commit_email).toBe("");
    expect(previewOf("noreply", PROFILE, "", "")).toBe(
      "Анна Петрова <u_1@noreply.studio.example.org>",
    );
  });
});

describe("профиль и смена почты", () => {
  it("сохраняет только изменённое имя", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <ProfileCard
        profile={PROFILE}
        emailVerified
        onSave={onSave}
        email={{ onSubmit: vi.fn() }}
      />,
    );
    await user.click(screen.getByTestId("profile-save"));
    expect(onSave).not.toHaveBeenCalled();
    const name = screen.getByLabelText("Имя");
    await user.clear(name);
    await user.type(name, "  Анна  Иванова ");
    await user.click(screen.getByTestId("profile-save"));
    expect(onSave).toHaveBeenCalledWith("Анна Иванова");
  });

  it("смена почты просит пароль и не принимает прежний адрес", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <ProfileCard
        profile={PROFILE}
        emailVerified={false}
        onSave={vi.fn()}
        email={{ onSubmit }}
      />,
    );
    expect(screen.getByText("Не подтверждена")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Сменить адрес" }));
    await user.type(screen.getByLabelText("Новый адрес"), "ANNA@example.org");
    await user.type(
      screen.getByLabelText("Пароль для подтверждения"),
      "secret",
    );
    await user.click(screen.getByRole("button", { name: "Отправить ссылку" }));
    expect(onSubmit).not.toHaveBeenCalled();
    const address = screen.getByLabelText("Новый адрес");
    await user.clear(address);
    await user.type(address, "anna@hse.ru");
    await user.click(screen.getByRole("button", { name: "Отправить ссылку" }));
    expect(onSubmit).toHaveBeenCalledWith({
      email: "anna@hse.ru",
      password: "secret",
    });
  });

  it("без SMTP ссылка подтверждения показывается на экране", async () => {
    const user = userEvent.setup();
    render(
      <ProfileCard
        profile={PROFILE}
        emailVerified
        onSave={vi.fn()}
        email={{
          onSubmit: vi.fn(),
          result: { status: "check_email", link: "https://x.example/c/1" },
        }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Сменить адрес" }));
    expect(screen.getByTestId("link-delivery")).toBeInTheDocument();
  });
});

describe("токены доступа", () => {
  it("форма отправляет название, права и срок, затем закрывается", async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn((_body: unknown, done: () => void) => {
      done();
    });
    render(
      <TokensCard
        status="ready"
        tokens={[]}
        onCreate={onCreate}
        onRevoke={vi.fn()}
      />,
    );
    expect(screen.getByTestId("tokens-empty")).toBeInTheDocument();
    await user.click(screen.getByTestId("token-new"));
    await user.type(screen.getByLabelText("Название"), "  CLI   дома ");
    await user.click(screen.getByTestId("token-scope-gitRead"));
    await user.click(screen.getByTestId("token-submit"));
    expect(onCreate).toHaveBeenCalledWith(
      { name: "CLI дома", scopes: ["api", "git:read"], expires_in_days: 90 },
      expect.any(Function),
    );
    expect(screen.queryByTestId("token-form")).toBeNull();
  });

  it("значение показано только пока передано в created", () => {
    const props = {
      status: "ready" as const,
      tokens: [],
      onCreate: vi.fn(),
      onRevoke: vi.fn(),
    };
    const { rerender } = render(
      <TokensCard
        {...props}
        created={{ token: "hsd_pat_SECRET", name: "A" }}
      />,
    );
    expect(screen.getByDisplayValue("hsd_pat_SECRET")).toBeInTheDocument();
    rerender(<TokensCard {...props} created={null} />);
    expect(screen.queryByDisplayValue("hsd_pat_SECRET")).toBeNull();
  });

  it("отзыв требует подтверждения", async () => {
    const user = userEvent.setup();
    const onRevoke = vi.fn();
    render(
      <TokensCard
        status="ready"
        tokens={[
          {
            id: "t1",
            name: "CI",
            prefix: "hsd_pat_9Zr",
            scopes: ["git:read"],
            created_at: "2026-09-01T09:00:00Z",
            expires_at: null,
            last_used_at: null,
          },
        ]}
        onCreate={vi.fn()}
        onRevoke={onRevoke}
      />,
    );
    expect(screen.getByText(/Бессрочный/)).toBeInTheDocument();
    await user.click(screen.getByTestId("token-revoke-t1"));
    expect(onRevoke).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("token-revoke-confirm-t1"));
    expect(onRevoke).toHaveBeenCalledWith("t1");
  });
});

describe("способы входа", () => {
  const PASSWORD = {
    id: "p",
    kind: "password" as const,
    provider_id: null,
    provider_label: "",
    email: "a@b.co",
    email_verified: null,
    can_unlink: false,
  };
  const SSO = {
    ...PASSWORD,
    id: "s",
    kind: "oidc" as const,
    provider_id: "keycloak",
    provider_label: "HSE SSO",
  };

  it("последний способ не отвязывается: вместо кнопки пояснение", () => {
    render(
      <IdentitiesCard
        status="ready"
        identities={[SSO]}
        providers={[{ id: "keycloak", label: "HSE SSO" }]}
        onLink={vi.fn()}
        onUnlink={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /Отвязать/ })).toBeNull();
    expect(screen.getByTestId("identity-locked-s")).toBeInTheDocument();
    expect(screen.getByTestId("identities-sole")).toBeInTheDocument();
  });

  it("отвязка идёт через подтверждение, привязка зовёт провайдера", async () => {
    const user = userEvent.setup();
    const onUnlink = vi.fn();
    const onLink = vi.fn();
    render(
      <IdentitiesCard
        status="ready"
        identities={[PASSWORD, { ...SSO, can_unlink: true }]}
        providers={[
          { id: "keycloak", label: "HSE SSO" },
          { id: "google", label: "Google" },
        ]}
        onLink={onLink}
        onUnlink={onUnlink}
      />,
    );
    await user.click(screen.getByTestId("identity-unlink-s"));
    expect(onUnlink).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("identity-unlink-confirm-s"));
    expect(onUnlink).toHaveBeenCalledWith("s");
    await user.click(screen.getByTestId("identity-link-google"));
    expect(onLink).toHaveBeenCalledWith("google");
    expect(screen.queryByTestId("identity-link-keycloak")).toBeNull();
  });

  it("отказ last_login_method объясняется", () => {
    render(
      <IdentitiesCard
        status="ready"
        identities={[PASSWORD, SSO]}
        failure={{ code: "last_login_method" }}
        onLink={vi.fn()}
        onUnlink={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("единственный способ");
  });
});
