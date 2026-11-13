import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { getCheckpointDeadlineGallery } from "./deadlineGallery";

describe("галерея сроков контрольных точек", () => {
  afterEach(cleanup);

  const entries = getCheckpointDeadlineGallery().flatMap((g) => g.entries);

  it("id записей уникальны и покрывают состояния 16.6", () => {
    const ids = entries.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(
      expect.arrayContaining([
        "deadline_none",
        "deadline_soon",
        "deadline_today",
        "deadline_packaged",
        "deadline_overdue",
        "chip_soon",
        "route_derived",
        "route_changed",
      ]),
    );
  });

  it.each(["ru", "en"])("записи рисуются без сервера (%s)", async (lng) => {
    await i18n.changeLanguage(lng);
    for (const entry of entries) {
      const { unmount, container } = render(
        <QueryClientProvider client={new QueryClient()}>
          {entry.render()}
        </QueryClientProvider>,
      );
      expect(container.textContent?.length ?? 0, entry.id).toBeGreaterThan(0);
      unmount();
    }
    await i18n.changeLanguage("ru");
  });
});
