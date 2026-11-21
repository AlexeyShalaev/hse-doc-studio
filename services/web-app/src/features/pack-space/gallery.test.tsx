import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { getPackSpaceGallery } from "./gallery";

describe("галерея нового интерфейса Студии", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  afterEach(cleanup);

  const entries = getPackSpaceGallery().flatMap((group) => group.entries);

  it("записи собраны из областей, id уникальны и начинаются с sp_", () => {
    const ids = entries.map((entry) => entry.id);
    expect(ids).toEqual(
      expect.arrayContaining([
        "sp_shell_desktop",
        "sp_shell_tablet",
        "sp_shell_phone",
      ]),
    );
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.every((id) => id.startsWith("sp_"))).toBe(true);
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
      expect(container.textContent?.length ?? 0, entry.id).toBeGreaterThan(0);
      // Ни одного ключа словаря вместо текста.
      expect(container.textContent, entry.id).not.toMatch(/\bshell\.[a-z]/);
      unmount();
    }
    await i18n.changeLanguage("ru");
  });
});
