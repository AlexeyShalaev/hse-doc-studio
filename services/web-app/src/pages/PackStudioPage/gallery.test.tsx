import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { i18n, loadAdminNamespaces } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { getPackStudioGallery } from "./gallery";

// CodeMirror в jsdom не поднимается: редактор подменён полем.
vi.mock("@shared/ui/CodeEditor", async () => {
  const { createElement } = await import("react");
  return {
    CodeEditor: ({ value }: { value: string }) =>
      createElement("textarea", { value, readOnly: true }),
  };
});

describe("галерея Студии шаблонов", () => {
  beforeAll(async () => {
    await Promise.all([
      loadPackStudioNamespace(),
      loadAdminNamespaces(["packStudio"]),
    ]);
  });
  afterEach(cleanup);

  const entries = getPackStudioGallery().flatMap((g) => g.entries);

  it("id записей уникальны", () => {
    const ids = entries.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
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
      expect(container.textContent, entry.id).not.toMatch(
        /(workspaces|problems|editor|grants|preview|service)\.[a-z]|git\.(ci|commit|branch|propose|access|fork|merge|diff|startOver)\b/,
      );
      unmount();
    }
    await i18n.changeLanguage("ru");
  });
});
