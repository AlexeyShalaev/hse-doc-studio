import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { AuthOptions, InvitationInfo } from "@entities/session";
import {
  RegisterCard,
  RegisterResultCard,
  RegisterUnavailableCard,
  REGISTER_ERROR_CODES,
  getSignUpGallery,
  registerAvailability,
  registerErrorKey,
} from "./index";

const AUTH: AuthOptions = {
  registration_mode: "open",
  password_enabled: true,
  oidc_providers: [],
  smtp_enabled: true,
  password_min_length: 10,
};
const INVITATION: InvitationInfo = {
  email: "maria.keller@example.org",
  invited_by: "Иван Сидоров",
  org_name: "МСПИН 2025",
};

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

const fill = (label: string, value: string) => {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
};

describe("sign-up", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("доступность по четырём режимам", () => {
    const of = (registration_mode: AuthOptions["registration_mode"]) =>
      registerAvailability({ ...AUTH, registration_mode }, false);
    expect(of("open")).toBe("form");
    expect(of("domains")).toBe("form");
    expect(of("invite")).toBe("invite_required");
    expect(of("closed")).toBe("closed");
    // Приглашение открывает форму даже в закрытом режиме, но не без паролей.
    expect(
      registerAvailability({ ...AUTH, registration_mode: "closed" }, true),
    ).toBe("form");
    expect(
      registerAvailability({ ...AUTH, password_enabled: false }, true),
    ).toBe("closed");
  });

  it("открытый режим: форма без подсказки про домены", () => {
    render(wrap(<RegisterCard auth={AUTH} onSubmit={() => undefined} />));
    expect(screen.getByTestId("register-form")).toBeInTheDocument();
    expect(screen.getByTestId("register-hint")).not.toHaveTextContent(
      "доменов",
    );
  });

  it("режим доменов: подсказка про разрешённые домены", () => {
    render(
      wrap(
        <RegisterCard
          auth={{ ...AUTH, registration_mode: "domains" }}
          onSubmit={() => undefined}
        />,
      ),
    );
    expect(screen.getByTestId("register-hint")).toHaveTextContent("доменов");
  });

  it("режим по приглашению: без ссылки формы нет", () => {
    render(wrap(<RegisterUnavailableCard reason="invite_required" />));
    expect(screen.queryByTestId("register-form")).toBeNull();
    expect(screen.getByTestId("register-unavailable")).toHaveAttribute(
      "aria-label",
      "Регистрация по приглашению",
    );
  });

  it("закрытый режим: сообщение и путь ко входу", () => {
    render(wrap(<RegisterUnavailableCard reason="closed" />));
    expect(screen.getByTestId("register-unavailable")).toHaveAttribute(
      "aria-label",
      "Регистрация закрыта",
    );
    expect(screen.getByRole("link", { name: /ко входу/ })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("приглашение: почта подставлена и заблокирована", () => {
    render(
      wrap(
        <RegisterCard
          auth={{ ...AUTH, registration_mode: "invite" }}
          invitation={INVITATION}
          onSubmit={() => undefined}
        />,
      ),
    );
    const email = screen.getByLabelText("Почта");
    expect(email).toHaveValue("maria.keller@example.org");
    expect(email).toHaveAttribute("readonly");
    expect(screen.getByTestId("register-hint")).toHaveTextContent("МСПИН 2025");
  });

  it("отправляет данные, пароли должны совпасть и быть не короче минимума", () => {
    const onSubmit = vi.fn();
    render(wrap(<RegisterCard auth={AUTH} onSubmit={onSubmit} />));
    fill("Имя", " Maria Keller ");
    fill("Почта", " maria@example.org ");
    fill("Пароль", "short");
    fill("Повторите пароль", "short");
    fireEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/короче 10 символов/)).toBeInTheDocument();

    fill("Пароль", "long enough pass");
    fill("Повторите пароль", "long enough pasz");
    expect(screen.getByText("Пароли не совпадают.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    expect(onSubmit).not.toHaveBeenCalled();

    fill("Повторите пароль", "long enough pass");
    fireEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "Maria Keller",
      email: "maria@example.org",
      password: "long enough pass",
    });
  });

  it("domain_not_allowed стоит рядом с полем почты", () => {
    render(
      wrap(
        <RegisterCard
          auth={AUTH}
          failure={{ code: "domain_not_allowed" }}
          onSubmit={() => undefined}
        />,
      ),
    );
    expect(screen.queryByTestId("register-error")).toBeNull();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("разрешённых доменов");
    expect(screen.getByLabelText("Почта").closest(".field")).toContainElement(
      alert,
    );
  });

  it("password_policy стоит рядом с полем пароля, прочее над формой", () => {
    const { unmount } = render(
      wrap(
        <RegisterCard
          auth={AUTH}
          failure={{ code: "password_policy" }}
          onSubmit={() => undefined}
        />,
      ),
    );
    expect(screen.getByLabelText("Пароль").closest(".field")).toContainElement(
      screen.getByRole("alert"),
    );
    unmount();
    render(
      wrap(
        <RegisterCard
          auth={AUTH}
          failure={{ code: "registration_closed" }}
          onSubmit={() => undefined}
        />,
      ),
    );
    expect(screen.getByTestId("register-error")).toBeInTheDocument();
  });

  it("итог нейтральный: текст не зависит от того, занят ли адрес", () => {
    const text = (link: string | null) => {
      const { unmount } = render(
        wrap(
          <RegisterResultCard
            status="check_email"
            link={link}
            email="a@example.org"
          />,
        ),
      );
      const out = screen.getByTestId("register-result").textContent;
      unmount();
      return out;
    };
    expect(text(null)).toContain("Если адрес a@example.org подходит");
    expect(text(null)).not.toMatch(/занят|уже зарегистр/i);
  });

  it("без SMTP ссылка показывается на экране, со SMTP её нет", () => {
    const link = "https://studio.example.org/verify/vf_x";
    const { unmount } = render(
      wrap(
        <RegisterResultCard status="check_email" link={link} email="a@b.org" />,
      ),
    );
    expect(screen.getByTestId("link-delivery")).toBeInTheDocument();
    expect(screen.getByLabelText("Ссылка подтверждения")).toHaveValue(link);
    unmount();
    render(
      wrap(
        <RegisterResultCard status="check_email" link={null} email="a@b.org" />,
      ),
    );
    expect(screen.queryByTestId("link-delivery")).toBeNull();
  });

  it("по приглашению на адрес письма не ждут: аккаунт готов к входу", () => {
    render(
      wrap(
        <RegisterResultCard
          status="check_email"
          link={null}
          email="a@b.org"
          invited
        />,
      ),
    );
    const result = screen.getByTestId("register-result");
    expect(result).toHaveTextContent("Аккаунт создан");
    expect(result).not.toHaveTextContent("Проверьте почту");
  });

  it("ждёт одобрения: свой итог без ссылки", () => {
    render(
      wrap(
        <RegisterResultCard
          status="pending_approval"
          link={null}
          email="a@b.org"
        />,
      ),
    );
    expect(screen.getByTestId("register-result")).toHaveAttribute(
      "data-tone",
      "warn",
    );
    expect(screen.queryByTestId("link-delivery")).toBeNull();
  });

  it("тексты отказов и итогов есть на ru и en, коды из каталога", async () => {
    const catalog = JSON.parse(
      readFileSync(
        join(
          import.meta.dirname,
          "../../../../../contracts/server/error_codes.json",
        ),
        "utf8",
      ),
    ) as string[];
    for (const code of REGISTER_ERROR_CODES) expect(catalog).toContain(code);
    for (const lng of ["ru", "en"]) {
      await i18n.changeLanguage(lng);
      for (const code of [...REGISTER_ERROR_CODES, "network", "unknown"]) {
        expect(i18n.exists(`auth:${registerErrorKey(code)}`), code).toBe(true);
      }
    }
  });

  it("все статические записи галереи рисуются", () => {
    const entries = getSignUpGallery()
      .flatMap((g) => g.entries)
      .filter((e) => e.scenario === undefined);
    expect(entries.length).toBeGreaterThan(10);
    for (const entry of entries) {
      const { container, unmount } = render(wrap(entry.render()));
      expect(container.textContent, entry.id).not.toBe("");
      expect(container.textContent, entry.id).not.toMatch(/register\.|auth:/);
      unmount();
    }
  });
});
