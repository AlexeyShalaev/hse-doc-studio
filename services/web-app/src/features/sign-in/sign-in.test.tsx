import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import { i18n } from "@shared/lib";
import type { AuthOptions } from "@entities/session";
import { AuthErrorCard, LoginCard } from "./index";
import { AUTH_ERROR_CODES } from "./lib/authErrorCodes";
import { LOGIN_ERROR_CODES, loginErrorKey } from "./lib/loginErrors";

const AUTH: AuthOptions = {
  registration_mode: "open",
  password_enabled: true,
  oidc_providers: [{ id: "hse", label: "HSE ID" }],
  smtp_enabled: true,
  password_min_length: 10,
};

const renderCard = (
  props: Partial<React.ComponentProps<typeof LoginCard>> = {},
) =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <LoginCard
          auth={AUTH}
          ssoHref={(id) => `#${id}`}
          onSubmit={() => undefined}
          {...props}
        />
      </MemoryRouter>
    </I18nextProvider>,
  );

describe("sign-in", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("после истёкшей сессии форма объясняет, почему она показана", () => {
    renderCard({ sessionEnded: true });
    expect(screen.getByTestId("login-session-ended")).toHaveTextContent(
      "Сессия закончилась",
    );
    cleanup();
    renderCard();
    expect(screen.queryByTestId("login-session-ended")).toBeNull();
  });

  it("тикающий отсчёт скрыт от скринридера, время объявлено один раз", () => {
    renderCard({
      failure: { code: "rate_limited", retryAfter: 30 },
    });
    expect(screen.getByTestId("login-countdown")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(screen.getByTestId("login-countdown-static")).toHaveTextContent(
      "30",
    );
  });

  it("во время отправки поля остаются фокусируемыми (readOnly, не disabled)", () => {
    renderCard({ pending: true });
    const email = screen.getByLabelText("Почта");
    expect(email).not.toBeDisabled();
    expect(email).toHaveAttribute("readonly");
    expect(
      screen.getByTestId("login-form").querySelector("button"),
    ).toHaveAttribute("aria-disabled", "true");
  });

  it("каждый код отказа показывает свой текст", () => {
    const seen = new Set<string>();
    for (const code of [...LOGIN_ERROR_CODES, "network", "unknown"]) {
      const { unmount } = renderCard({ failure: { code, retryAfter: 5 } });
      const text =
        screen.getByTestId("login-error").getAttribute("aria-label") ?? "";
      expect(text, code).not.toBe("");
      expect(text).not.toContain("login.errors");
      seen.add(text);
      unmount();
    }
    expect(seen.size).toBe(LOGIN_ERROR_CODES.length + 2);
  });

  it("тексты кодов есть на ru и en", async () => {
    for (const lng of ["ru", "en"]) {
      await i18n.changeLanguage(lng);
      for (const code of [...LOGIN_ERROR_CODES, "network", "unknown"]) {
        expect(
          i18n.exists(`auth:${loginErrorKey(code)}`),
          `${lng} ${code}`,
        ).toBe(true);
      }
      for (const code of [...AUTH_ERROR_CODES, "unknown"]) {
        expect(
          i18n.exists(`auth:authError.codes.${code}.title`),
          `${lng} ${code}`,
        ).toBe(true);
      }
    }
  });

  it("коды входа совпадают с каталогом ошибок", () => {
    const catalog = JSON.parse(
      readFileSync(
        join(
          import.meta.dirname,
          "../../../../../contracts/server/error_codes.json",
        ),
        "utf8",
      ),
    ) as string[];
    for (const code of LOGIN_ERROR_CODES) expect(catalog).toContain(code);
  });

  it("SSO-only: формы нет, есть кнопка провайдера", () => {
    renderCard({
      auth: { ...AUTH, password_enabled: false, registration_mode: "closed" },
    });
    expect(screen.queryByTestId("login-form")).toBeNull();
    expect(screen.getByRole("link", { name: /HSE ID/ })).toHaveAttribute(
      "href",
      "#hse",
    );
    expect(screen.queryByText("или")).toBeNull();
  });

  it("отправляет почту и пароль", () => {
    const onSubmit = vi.fn();
    renderCard({ onSubmit });
    fireEvent.change(screen.getByLabelText("Почта"), {
      target: { value: " a@b.org " },
    });
    fireEvent.change(screen.getByLabelText("Пароль"), {
      target: { value: "secret-pass-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(onSubmit).toHaveBeenCalledWith("a@b.org", "secret-pass-1");
  });

  it("rate_limited: таймер блокирует кнопку до нуля", () => {
    vi.useFakeTimers();
    renderCard({
      failure: { code: "rate_limited", retryAfter: 2 },
      initialEmail: "a@b.org",
    });
    fireEvent.change(screen.getByLabelText("Пароль"), {
      target: { value: "secret-pass-1" },
    });
    expect(screen.getByTestId("login-countdown")).toHaveTextContent("2");
    expect(screen.getByRole("button", { name: "Войти" })).toBeDisabled();
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByTestId("login-countdown")).toHaveTextContent("1");
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.queryByTestId("login-error")).toBeNull();
    expect(screen.getByRole("button", { name: "Войти" })).toBeEnabled();
  });

  it("/auth/error: у каждого кода свой заголовок", () => {
    const titles = new Set<string>();
    for (const code of [...AUTH_ERROR_CODES, "unknown" as const]) {
      const { unmount } = render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <AuthErrorCard code={code} />
          </MemoryRouter>
        </I18nextProvider>,
      );
      titles.add(
        screen.getByTestId("auth-error-frame").getAttribute("aria-label") ?? "",
      );
      unmount();
    }
    expect(titles.size).toBe(AUTH_ERROR_CODES.length + 1);
  });
});
