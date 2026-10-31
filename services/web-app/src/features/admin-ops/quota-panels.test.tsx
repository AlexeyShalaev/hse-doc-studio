import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { ensureAdminOpsLocales } from "./lib/locales";
import { QuotasPage, RunnersPage } from "./index";
import { autoscaleFromDraft } from "./ui/AutoscalePanel";
import { policyFromDraft } from "./ui/QuotaPolicyPanel";
import { resourcesFor } from "./ui/QuotaOverridesPanel";

const wrap = (node: React.ReactNode) => (
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
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

describe("квоты по видам ресурсов: чистая логика форм", () => {
  const draft = {
    values: {
      storage: { user: "2", org: "" },
      builds: { user: "30", org: "" },
      ai_tokens_day: { user: "", org: "" },
      ai_tokens_month: { user: "200000", org: "" },
      members: { user: "5", org: "" },
    },
    warn: "80",
    onExceed: "deprioritize" as const,
  };

  it("место вводится в гигабайтах и уходит в байтах", () => {
    const body = policyFromDraft(draft);
    expect(body?.defaults.find((d) => d.kind === "storage")?.user).toBe(
      2 * 1024 ** 3,
    );
    expect(body?.defaults.find((d) => d.kind === "builds")?.org).toBeNull();
  });

  it("неверное число или процент дают null", () => {
    expect(
      policyFromDraft({
        ...draft,
        values: { ...draft.values, builds: { user: "-3", org: "" } },
      }),
    ).toBeNull();
    expect(policyFromDraft({ ...draft, warn: "0" })).toBeNull();
    expect(policyFromDraft({ ...draft, warn: "101" })).toBeNull();
  });

  it("у человека нет значений «на организацию»", () => {
    expect(resourcesFor("user").some((r) => r.endsWith("_org"))).toBe(false);
    expect(resourcesFor("org")).toContain("storage.bytes_org");
  });

  it("автомасштабирование: максимум не меньше минимума, webhook требует адрес", () => {
    const base = {
      mode: "compose" as const,
      url: "",
      min_runners: "1",
      max_runners: "6",
      target_queue_per_slot: "2",
      scale_up_wait_s: "30",
      cooldown_up_s: "60",
      cooldown_down_s: "300",
      idle_before_down_s: "300",
      step_up: "2",
      step_down: "1",
    };
    expect(autoscaleFromDraft(base)?.max_runners).toBe(6);
    expect(autoscaleFromDraft({ ...base, min_runners: "7" })).toBeNull();
    expect(autoscaleFromDraft({ ...base, mode: "webhook" })).toBeNull();
    expect(
      autoscaleFromDraft({
        ...base,
        mode: "webhook",
        url: "https://o.example/scale",
      })?.webhook_url,
    ).toBe("https://o.example/scale");
    expect(autoscaleFromDraft({ ...base, url: "ftp://x" })).toBeNull();
  });
});

describe("квоты по видам ресурсов: экраны админки", () => {
  beforeAll(() => {
    installServerDemo();
    // Radix Select в jsdom ждёт методов, которых там нет.
    const proto = Element.prototype as unknown as Record<string, unknown>;
    proto.hasPointerCapture ??= () => false;
    proto.setPointerCapture ??= () => undefined;
    proto.releasePointerCapture ??= () => undefined;
    proto.scrollIntoView ??= () => undefined;
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    await ensureAdminOpsLocales();
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("умолчания: правка места в ГБ сохраняется, пустое поле снимает предел", async () => {
    const user = userEvent.setup();
    render(wrap(<QuotasPage />));
    const storage = await screen.findByTestId("policy-storage-user");
    expect(storage).toHaveValue(2);
    expect(screen.getByTestId("quota-policy-save")).toBeDisabled();

    await user.clear(storage);
    await user.type(storage, "3.5");
    await user.clear(screen.getByTestId("policy-builds-user"));
    await user.click(screen.getByTestId("quota-policy-save"));

    expect(await screen.findByTestId("quota-policy-saved")).toBeVisible();
    await waitFor(() => {
      expect(screen.getByTestId("policy-storage-user")).toHaveValue(3.5);
    });
    expect(screen.getByTestId("policy-builds-user")).toHaveValue(null);
  }, 20_000);

  it("неверное значение не уходит на сервер и объясняется", async () => {
    const user = userEvent.setup();
    render(wrap(<QuotasPage />));
    const warn = await screen.findByTestId("policy-warn");
    await user.clear(warn);
    await user.type(warn, "0");
    await user.click(screen.getByTestId("quota-policy-save"));

    expect(
      await screen.findByText("Проверьте числа: положительные, без букв."),
    ).toBeVisible();
    expect(screen.queryByTestId("quota-policy-saved")).toBeNull();
  }, 20_000);

  it("переопределения: список с названием владельца и снятие", async () => {
    const user = userEvent.setup();
    render(wrap(<QuotasPage />));
    await waitFor(() => {
      expect(screen.getByText("Факультет компьютерных наук")).toBeVisible();
    });
    const table = screen.getByRole("table", { name: "Переопределения" });
    expect(within(table).getByText("Место (на организацию)")).toBeVisible();
    expect(within(table).getByText(/50\s?ГБ/)).toBeVisible();

    await user.click(
      screen.getByRole("button", {
        name: "Снять переопределение: Факультет компьютерных наук",
      }),
    );
    await waitFor(() => {
      expect(screen.queryByText("Факультет компьютерных наук")).toBeNull();
    });
  }, 20_000);

  it("ИИ-шлюз: провайдер, состояние автомата и счётчики за сутки", async () => {
    render(wrap(<QuotasPage />));
    const gateway = await screen.findByTestId("ai-gateway");
    expect(await within(gateway).findByText("OpenAI общий")).toBeVisible();
    expect(within(gateway).getByText("Работает")).toBeVisible();
    expect(within(gateway).getByText("340")).toBeVisible();
  }, 20_000);

  it("использование: итоги установки за период", async () => {
    render(wrap(<QuotasPage />));
    const totals = await screen.findByTestId("usage-totals");
    await waitFor(() => {
      expect(totals).toHaveTextContent("412");
    });
    expect(screen.getByTestId("quota-usage")).toHaveTextContent("2026-11-01");
  }, 20_000);

  it("автомасштабирование: метрики, решение и сохранение режима webhook с адресом", async () => {
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));
    const decision = await screen.findByTestId("autoscale-decision");
    expect(decision).toHaveAttribute("data-action", "up");
    expect(decision).toHaveTextContent("очередь длиннее нормы");
    expect(screen.getByTestId("autoscale-queued")).toHaveTextContent("9");
    expect(screen.getByTestId("autoscale-save")).toBeDisabled();

    await user.click(screen.getByRole("combobox", { name: "Режим" }));
    await user.click(
      await screen.findByRole("option", { name: "Внешний webhook" }),
    );
    await user.click(screen.getByTestId("autoscale-save"));
    expect(await screen.findByText(/Проверьте значения/)).toBeVisible();

    await user.type(
      screen.getByTestId("autoscale-url"),
      "https://orch.example/scale",
    );
    await user.click(screen.getByTestId("autoscale-save"));
    await waitFor(() => {
      expect(screen.getByTestId("autoscale-save")).toBeDisabled();
    });
    expect(screen.getByTestId("autoscale-url")).toHaveValue(
      "https://orch.example/scale",
    );
  }, 20_000);
});
