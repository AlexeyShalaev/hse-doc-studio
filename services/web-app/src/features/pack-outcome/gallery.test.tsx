import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { getPackOutcomeGallery } from "./gallery";

describe("галерея экрана «Результат»", () => {
  beforeAll(async () => {
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
  });
  afterEach(cleanup);

  const entries = getPackOutcomeGallery().flatMap((g) => g.entries);

  it("id записей уникальны, записей хватает на все состояния", () => {
    const ids = entries.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(
      expect.arrayContaining([
        "po_result",
        "po_loading",
        "po_unreadable",
        "po_empty",
        "po_sections_points",
        "po_sections_route",
        "po_checks",
        "po_checks_error",
        "po_branches",
        "po_branches_error",
      ]),
    );
  });

  it.each(["ru", "en"])("записи рисуются без сервера (%s)", async (lng) => {
    await i18n.changeLanguage(lng);
    for (const entry of entries) {
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
      });
      entry.seed?.(client);
      const { container, unmount } = render(
        <QueryClientProvider client={client}>
          <MemoryRouter>{entry.render()}</MemoryRouter>
        </QueryClientProvider>,
      );
      expect(container.textContent.length, entry.id).toBeGreaterThan(0);
      // Ни одного ключа словаря вместо текста.
      expect(container.textContent, entry.id).not.toMatch(
        /\b(bar|status|panels|inputs|result|sections|rules|footer|errors|points|route|reasons)\.[a-z]/,
      );
      unmount();
    }
    await i18n.changeLanguage("ru");
  });

  it("запись с адресом показывает состояние из query", async () => {
    await i18n.changeLanguage("ru");
    const entry = entries.find((e) => e.id === "po_state_in_url");
    expect(entry).toBeDefined();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      container.querySelector('[data-testid="outcome-selected"]')?.textContent,
    ).toContain("operator_manual");
    expect(
      container.querySelector('[data-testid="outcome-input-kind"]')
        ?.textContent,
    ).toContain("research");
  });

  it("запись маршрута рисует параллельный шаг и пропущенную пару", async () => {
    await i18n.changeLanguage("ru");
    const entry = entries.find((e) => e.id === "po_sections_route");
    expect(entry).toBeDefined();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
    const lane = container.querySelector(
      '[data-testid="outcome-route-pdp-application-steps"]',
    );
    expect(lane?.tagName).toBe("OL");
    expect(lane?.querySelectorAll("li")).toHaveLength(2);
    expect(
      container.querySelector('[data-testid="outcome-step-pdp-application-2"]')
        ?.textContent,
    ).toContain("параллельно");
    expect(
      container.querySelector(
        '[data-testid="outcome-route-pdp-application-skipped"]',
      ),
    ).not.toBeNull();
  });

  it.each([
    ["po_checks", "outcome-check-gost-7.32-2017/line-spacing"],
    ["po_branches", "outcome-branch-staffing"],
  ])(
    "запись %s показывает раскрытый раздел с данными из кэша",
    (id, testId) => {
      const entry = entries.find((e) => e.id === id);
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
      });
      entry?.seed?.(client);
      const { container } = render(
        <QueryClientProvider client={client}>
          <MemoryRouter>{entry?.render()}</MemoryRouter>
        </QueryClientProvider>,
      );
      expect(
        container.querySelector(`[data-testid="${testId}"]`),
      ).not.toBeNull();
    },
  );

  it.each(["po_checks_error", "po_branches_error"])(
    "запись %s показывает сбой запроса части",
    (id) => {
      const entry = entries.find((e) => e.id === id);
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
      });
      entry?.seed?.(client);
      const { container } = render(
        <QueryClientProvider client={client}>
          <MemoryRouter>{entry?.render()}</MemoryRouter>
        </QueryClientProvider>,
      );
      expect(container.querySelector('[role="alert"]')).not.toBeNull();
    },
  );
});
