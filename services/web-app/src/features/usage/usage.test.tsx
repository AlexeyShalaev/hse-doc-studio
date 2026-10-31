import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { MyUsage, UsageLine } from "@entities/quota";
import { UsageSection } from "./ui/UsageSection";
import { UsageView } from "./ui/UsageView";

const api = vi.hoisted(() => ({ mine: vi.fn() }));

vi.mock("@entities/quota/api/quotaApi", async () => ({
  ...(await vi.importActual<Record<string, unknown>>(
    "@entities/quota/api/quotaApi",
  )),
  usageApi: { mine: api.mine, org: vi.fn() },
}));

const line = (
  patch: Partial<UsageLine> & Pick<UsageLine, "kind">,
): UsageLine => ({
  scope: "user",
  unit: "builds",
  used: 0,
  limit: null,
  percent: null,
  state: "unlimited",
  source: null,
  resets_at: null,
  ...patch,
});

const USAGE: MyUsage = {
  warn_percent: 80,
  user: {
    owner_id: "u1",
    owner_name: "Анна",
    lines: [
      line({
        kind: "storage",
        unit: "bytes",
        used: 1100 * 1024 ** 2,
        limit: 1024 ** 3,
        percent: 100,
        state: "exceeded",
        source: "installation",
      }),
      line({
        kind: "builds",
        used: 27,
        limit: 30,
        percent: 90,
        state: "warning",
        source: "user",
        resets_at: "2026-12-01T00:00:00Z",
      }),
      line({ kind: "ai_tokens_day", used: 1200 }),
      line({
        kind: "ai_tokens_month",
        used: 50,
        limit: 1000,
        percent: 5,
        state: "ok",
        source: "org",
        resets_at: "2026-12-01T00:00:00Z",
      }),
    ],
  },
  orgs: [
    {
      owner_id: "org_hse",
      owner_name: "Кафедра",
      lines: [
        line({
          kind: "builds",
          scope: "org",
          used: 3,
          limit: 100,
          percent: 3,
          state: "ok",
          source: "org",
          resets_at: "2026-12-01T00:00:00Z",
        }),
      ],
    },
  ],
};

const wrap = (node: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {node}
    </QueryClientProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("раздел «Использование»", () => {
  it("показывает значения, пределы, источник и дату сброса, состояния отличаются", async () => {
    api.mine.mockResolvedValue(USAGE);
    wrap(<UsageSection />);

    const storage = await screen.findByTestId("usage-storage");
    expect(storage).toHaveAttribute("data-state", "exceeded");
    expect(storage).toHaveTextContent("1,1 ГБ из 1 ГБ");
    expect(storage).toHaveTextContent("Исчерпано");

    const builds = screen.getAllByTestId("usage-builds")[0];
    expect(builds).toHaveAttribute("data-state", "warning");
    expect(builds).toHaveTextContent("27 из 30");
    expect(builds).toHaveTextContent("Ваше значение");
    expect(builds).toHaveTextContent("сброс 1 декабря");
    expect(screen.getAllByRole("progressbar")[1]).toHaveAttribute(
      "aria-valuenow",
      "90",
    );
  });

  it("у вида без предела полосы нет, есть пометка «без предела»", async () => {
    api.mine.mockResolvedValue(USAGE);
    wrap(<UsageSection />);

    const day = await screen.findByTestId("usage-ai_tokens_day");
    expect(day).toHaveTextContent("без предела");
    expect(day.querySelector("[role=progressbar]")).toBeNull();
  });

  it("организации идут отдельными блоками со своим названием", async () => {
    api.mine.mockResolvedValue(USAGE);
    wrap(<UsageSection />);

    const org = await screen.findByTestId("usage-org-org_hse");
    expect(org).toHaveTextContent("Организация «Кафедра»");
    expect(org).toHaveTextContent("3 из 100");
  });

  it("на английском даты и подписи тоже на английском", async () => {
    await i18n.changeLanguage("en");
    api.mine.mockResolvedValue(USAGE);
    wrap(<UsageSection />);

    const builds = (await screen.findAllByTestId("usage-builds"))[0];
    expect(builds).toHaveTextContent("27 of 30");
    expect(builds).toHaveTextContent("resets December 1");
  });

  it("при ошибке загрузки есть кнопка повтора", async () => {
    api.mine.mockRejectedValueOnce(new Error("boom"));
    api.mine.mockResolvedValue(USAGE);
    wrap(<UsageSection />);

    const retry = await screen.findByRole("button", { name: "Повторить" });
    retry.click();

    await waitFor(() => {
      expect(screen.getByTestId("usage-storage")).toBeInTheDocument();
    });
  });

  it("в состоянии загрузки показывает статус", () => {
    wrap(<UsageView status="loading" />);
    expect(screen.getByText("Загружаем использование…")).toBeInTheDocument();
  });
});
