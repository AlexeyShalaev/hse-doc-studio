import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import {
  ForgotCard,
  ForgotSentCard,
  RECOVERY_ERROR_CODES,
  ResetCard,
  ResetDoneCard,
  ResetExpiredCard,
  VerifyCard,
  getRecoveryGallery,
  recoveryErrorKey,
} from "./index";

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

const fill = (label: string, value: string) => {
  fireEvent.change(screen.getByLabelText(label, { selector: "input" }), {
    target: { value },
  });
};

const resendProps = {
  smtp: true,
  onSubmit: () => undefined,
};

describe("account-recovery", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("forgot: отправляет обрезанную почту", () => {
    const onSubmit = vi.fn();
    render(wrap(<ForgotCard onSubmit={onSubmit} />));
    expect(
      screen.getByRole("button", { name: "Отправить ссылку" }),
    ).toBeDisabled();
    fill("Почта", " anna@example.org ");
    fireEvent.click(screen.getByRole("button", { name: "Отправить ссылку" }));
    expect(onSubmit).toHaveBeenCalledWith("anna@example.org");
  });

  it("forgot: итог нейтральный и не выдаёт существование аккаунта", () => {
    render(wrap(<ForgotSentCard email="x@example.org" link={null} smtp />));
    const text = screen.getByTestId("forgot-sent").textContent ?? "";
    expect(text).toContain("Если для адреса x@example.org есть аккаунт");
    expect(text).not.toMatch(/не найден|не существует|нет такого/i);
  });

  it("forgot без SMTP: ссылка копируемая, а без ссылки просьба к администратору", () => {
    const link = "https://studio.example.org/reset/rs_x";
    const { unmount } = render(
      wrap(<ForgotSentCard email="x@example.org" link={link} smtp={false} />),
    );
    expect(screen.getByLabelText("Ссылка для нового пароля")).toHaveValue(link);
    unmount();
    render(
      wrap(<ForgotSentCard email="x@example.org" link={null} smtp={false} />),
    );
    expect(screen.queryByTestId("link-delivery")).toBeNull();
    expect(screen.getByTestId("forgot-sent")).toHaveTextContent(
      "обратитесь к администратору",
    );
  });

  it("reset: пароль не короче минимума и совпадает с повтором", () => {
    const onSubmit = vi.fn();
    render(wrap(<ResetCard minLength={12} onSubmit={onSubmit} />));
    fill("Новый пароль", "short pass");
    fill("Повторите пароль", "short pass");
    fireEvent.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/короче 12 символов/)).toBeInTheDocument();
    fill("Новый пароль", "a much longer passphrase");
    fill("Повторите пароль", "a much longer passphrasX");
    expect(screen.getByText("Пароли не совпадают.")).toBeInTheDocument();
    fill("Повторите пароль", "a much longer passphrase");
    fireEvent.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(onSubmit).toHaveBeenCalledWith("a much longer passphrase");
  });

  it("reset: password_policy у поля пароля", () => {
    render(
      wrap(
        <ResetCard
          minLength={10}
          failure={{ code: "password_policy" }}
          onSubmit={() => undefined}
        />,
      ),
    );
    expect(
      screen
        .getByLabelText("Новый пароль", { selector: "input" })
        .closest(".field"),
    ).toContainElement(screen.getByRole("alert"));
  });

  it("reset: просроченная ссылка ведёт к новому запросу, успех ко входу", () => {
    const { unmount } = render(wrap(<ResetExpiredCard />));
    expect(screen.getByTestId("reset-expired")).toHaveAttribute(
      "aria-label",
      "Ссылка недействительна или просрочена",
    );
    expect(
      screen.getByRole("link", { name: "Запросить новую ссылку" }),
    ).toHaveAttribute("href", "/forgot");
    unmount();
    render(wrap(<ResetDoneCard />));
    expect(screen.getByRole("link", { name: /ко входу/ })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("verify: состояния проверки, успеха и просрочки", () => {
    const { unmount: u1 } = render(
      wrap(<VerifyCard state="checking" resend={resendProps} />),
    );
    expect(screen.getByTestId("verify-checking")).toBeInTheDocument();
    u1();
    const { unmount: u2 } = render(
      wrap(<VerifyCard state="done" resend={resendProps} />),
    );
    expect(screen.getByTestId("verify-done")).toBeInTheDocument();
    u2();
    render(wrap(<VerifyCard state="invalid" resend={resendProps} />));
    expect(screen.getByTestId("verify-invalid")).toHaveAttribute(
      "aria-label",
      "Ссылка недействительна или просрочена",
    );
    expect(screen.getByTestId("verify-resend-form")).toBeInTheDocument();
  });

  it("verify: повторная отправка со своим итогом и ссылкой без SMTP", () => {
    const onSubmit = vi.fn();
    const { unmount } = render(
      wrap(
        <VerifyCard state="invalid" resend={{ ...resendProps, onSubmit }} />,
      ),
    );
    fill("Почта", "anna@example.org");
    fireEvent.click(
      screen.getByRole("button", { name: "Отправить ссылку ещё раз" }),
    );
    expect(onSubmit).toHaveBeenCalledWith("anna@example.org");
    unmount();
    render(
      wrap(
        <VerifyCard
          state="invalid"
          resend={{
            smtp: false,
            onSubmit,
            sent: {
              email: "anna@example.org",
              link: "https://s.example.org/verify/vf_n",
            },
          }}
        />,
      ),
    );
    expect(screen.queryByTestId("verify-resend-form")).toBeNull();
    expect(screen.getByLabelText("Ссылка подтверждения")).toHaveValue(
      "https://s.example.org/verify/vf_n",
    );
  });

  it("verify: сервер не ответил, повтор доступен", () => {
    const onRetry = vi.fn();
    render(
      wrap(
        <VerifyCard
          state="unreachable"
          resend={resendProps}
          onRetry={onRetry}
        />,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("тексты отказов есть на ru и en", async () => {
    for (const lng of ["ru", "en"]) {
      await i18n.changeLanguage(lng);
      for (const code of [...RECOVERY_ERROR_CODES, "network", "unknown"]) {
        expect(i18n.exists(`auth:${recoveryErrorKey(code)}`), code).toBe(true);
      }
    }
  });

  it("все статические записи галереи рисуются", () => {
    const entries = getRecoveryGallery()
      .flatMap((g) => g.entries)
      .filter((e) => e.scenario === undefined);
    expect(entries.length).toBeGreaterThan(15);
    for (const entry of entries) {
      const { container, unmount } = render(wrap(entry.render()));
      expect(container.textContent, entry.id).not.toBe("");
      expect(container.textContent, entry.id).not.toMatch(
        /recovery\.|forgot\.|verify\./,
      );
      unmount();
    }
  });
});
