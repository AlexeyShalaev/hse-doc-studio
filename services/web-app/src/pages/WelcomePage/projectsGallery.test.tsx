import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { getProjectsGallery } from "./projectsGallery";

describe("галерея проектов сервера", () => {
  afterEach(cleanup);

  const entries = getProjectsGallery().flatMap((group) => group.entries);

  it("есть карточки, пустые состояния и живые экраны", () => {
    const ids = entries.map((entry) => entry.id);
    expect(ids).toEqual(
      expect.arrayContaining([
        "card_own",
        "card_org_reviewer",
        "list_empty_server",
        "list_load_error",
        "live_create_wizard",
        "live_clone_wizard",
      ]),
    );
    expect(new Set(ids).size).toBe(ids.length);
  });

  it.each(["ru", "en"])(
    "статичные записи рисуются без сервера (%s)",
    async (lng) => {
      await i18n.changeLanguage(lng);
      for (const entry of entries.filter((e) => e.scenario === undefined)) {
        const { unmount, container } = render(
          <QueryClientProvider client={new QueryClient()}>
            <MemoryRouter>{entry.render()}</MemoryRouter>
          </QueryClientProvider>,
        );
        expect(container.textContent?.length ?? 0, entry.id).toBeGreaterThan(0);
        unmount();
      }
      await i18n.changeLanguage("ru");
    },
  );
});
