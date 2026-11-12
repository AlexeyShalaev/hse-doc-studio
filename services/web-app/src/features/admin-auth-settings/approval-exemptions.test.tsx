import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { AdminAuthSettings } from "./index";
import {
  MAX_EXEMPTIONS,
  checkAddress,
  parseExemption,
  parseExemptions,
  ruleMatches,
} from "./lib/approvalExemptions";

// Исключения из одобрения: тот же разбор, что на сервере
// (tests/unit/core/test_approval_exemptions.py), и поле в разделе «Регистрация».

describe("разбор исключений из одобрения", () => {
  it.each([
    [" HSE.Ru ", "hse.ru"],
    ["@hse.ru", "hse.ru"],
    ["*.EDU.hse.ru", "*.edu.hse.ru"],
    ["Name@Example.COM", "name@example.com"],
    ["ВШЭ.РФ", "вшэ.рф"],
    ["xn--80aswg.xn--p1ai", "xn--80aswg.xn--p1ai"],
  ])("%s читается как %s", (raw, rule) => {
    expect(parseExemption(raw)).toEqual({ rule });
  });

  it.each([
    ["hse", "domain"],
    ["hse.ru.", "domain"],
    ["*.ru", "domain"],
    ["hse.ru$", "domain"],
    ["^.*@hse\\.ru$", "wildcard"],
    ["*hse.ru", "wildcard"],
    ["*@hse.ru", "wildcard"],
    ["a@b@hse.ru", "address"],
    ["a".repeat(260) + ".ru", "too_long"],
  ])("%s отклоняется: %s", (raw, issue) => {
    expect(parseExemption(raw)).toEqual({ issue });
  });

  it("строки с номерами, пустые пропускаются, повторы схлопываются", () => {
    expect(parseExemptions("hse.ru\n\nHSE.ru\nhse\n*.hse.ru")).toEqual({
      rules: ["hse.ru", "*.hse.ru"],
      problems: [{ line: 4, value: "hse", issue: "domain" }],
      tooMany: false,
    });
    const many = Array.from(
      { length: MAX_EXEMPTIONS + 1 },
      (_, i) => `u${String(i)}@hse.ru`,
    );
    expect(parseExemptions(many.join("\n")).tooMany).toBe(true);
  });

  it.each([
    ["hse.ru", "ann@HSE.ru", true],
    ["hse.ru", "ann@nothse.ru", false],
    ["hse.ru", "ann@hse.ru.evil.com", false],
    ["*.hse.ru", "ann@edu.hse.ru", true],
    ["*.hse.ru", "ann@hse.ru", false],
    ["*.hse.ru", "ann@evil-hse.ru", false],
    ["name@example.com", "NAME@example.com", true],
  ])("%s и %s: %s", (rule, email, matches) => {
    expect(ruleMatches(rule, email)).toBe(matches);
  });

  it("проверка адреса учитывает режим, домены, одобрение и почту", () => {
    const base = {
      mode: "open" as const,
      domains: [],
      approval: true,
      rules: ["*.hse.ru"],
      smtpEnabled: true,
    };
    expect(checkAddress("ann@edu.hse.ru", base)).toEqual({
      kind: "exempt",
      rule: "*.hse.ru",
    });
    expect(checkAddress("ann@gmail.com", base).kind).toBe("approval");
    expect(checkAddress("ann", base).kind).toBe("invalid");
    expect(
      checkAddress("ann@edu.hse.ru", { ...base, smtpEnabled: false }),
    ).toEqual({ kind: "exemptNoSmtp", rule: "*.hse.ru" });
    expect(
      checkAddress("ann@edu.hse.ru", {
        ...base,
        mode: "domains",
        domains: ["hse.ru"],
      }).kind,
    ).toBe("domain");
    expect(
      checkAddress("ann@gmail.com", { ...base, approval: false }).kind,
    ).toBe("noApproval");
    expect(
      checkAddress("ann@gmail.com", {
        ...base,
        approval: false,
        smtpEnabled: false,
      }).kind,
    ).toBe("inviteOnly");
    expect(checkAddress("ann@hse.ru", { ...base, mode: "invite" }).kind).toBe(
      "inviteOnly",
    );
  });
});

const mount = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: {
              queries: { retry: false },
              mutations: { retry: false },
            },
          })
        }
      >
        <MemoryRouter initialEntries={["/admin/settings"]}>
          <AdminAuthSettings />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

describe("поле «Без одобрения для адресов»", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("появляется с одобрением, проверяет строки и сохраняет правила", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByTestId("registration-form");
    await user.click(screen.getByTestId("registration-mode-open"));
    expect(screen.queryByTestId("registration-exemptions")).toBeNull();
    await user.click(screen.getByTestId("registration-approval"));

    const field = screen.getByLabelText("Без одобрения для адресов");
    await user.type(field, "hse{Enter}*hse.ru");
    const errors = screen.getByTestId("registration-exemptions-errors");
    expect(errors).toHaveTextContent(
      "Строка 1 «hse»: это не домен, ожидается вид hse.ru.",
    );
    expect(errors).toHaveTextContent("Строка 2 «*hse.ru»: звёздочка");
    expect(screen.getByTestId("save-bar-save")).toBeDisabled();

    await user.clear(field);
    await user.type(field, "HSE.ru{Enter}*.hse.ru{Enter}Rector@Example.org");
    expect(screen.queryByTestId("registration-exemptions-errors")).toBeNull();

    const probe = screen.getByLabelText("Проверить адрес");
    await user.type(probe, "ann@edu.hse.ru");
    expect(screen.getByTestId("registration-check-result")).toHaveTextContent(
      "Одобрение не нужно по правилу *.hse.ru",
    );
    await user.clear(probe);
    await user.type(probe, "ann@gmail.com");
    expect(screen.getByTestId("registration-check-result")).toHaveTextContent(
      "Нужно одобрение администратора.",
    );

    await user.click(screen.getByTestId("save-bar-save"));
    await waitFor(() => {
      expect(screen.queryByTestId("save-bar")).toBeNull();
    });
    expect(screen.getByLabelText("Без одобрения для адресов")).toHaveValue(
      "hse.ru\n*.hse.ru\nrector@example.org",
    );
  });

  it("без почты предупреждает, что исключения не действуют", async () => {
    activateServerScenario("admin_sso");
    const user = userEvent.setup();
    mount();
    await screen.findByTestId("registration-form");
    await user.click(screen.getByTestId("registration-mode-domains"));
    await user.click(screen.getByTestId("registration-approval"));
    expect(
      screen.getByText(/При регистрации с паролем исключения не действуют/),
    ).toBeVisible();
  });

  it("заданные окружением исключения только читаются", async () => {
    activateServerScenario("admin_env_locked");
    mount();
    const field = await screen.findByTestId("registration-exemptions-input");
    expect(field).toHaveAttribute("readonly");
    expect(field).toHaveValue("*.hse.ru");
    expect(screen.getByTestId("registration-exemptions-locked")).toBeVisible();
  });
});
