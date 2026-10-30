import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import { getMyRunnersGallery } from "@features/my-runners";
import { getRemoteRunnerGallery } from "@features/remote-runner";
import { getRelayGallery } from "@features/agent-chat";
import { getBuildStatesGallery } from "@features/build-states";
import { getAdminOpsGallery } from "@features/admin-ops";
import { ensureAdminOpsLocales } from "@features/admin-ops/lib/locales";
import { getRunnerPairGallery } from "@pages/RunnerPairPage";

// Галереи личных раннеров: каждое состояние без демо-мира рисуется на обоих
// языках и не показывает сырых ключей перевода.

const PERSONAL_GROUPS = new Set([
  "build-placement",
  "project-builds",
  "admin-ops-personal",
]);

const groups = (): GalleryGroup[] => [
  ...getMyRunnersGallery(),
  ...getRemoteRunnerGallery(),
  ...getRelayGallery(),
  ...getRunnerPairGallery(),
  ...getBuildStatesGallery().filter((g) => PERSONAL_GROUPS.has(g.id)),
  ...getAdminOpsGallery().filter((g) => PERSONAL_GROUPS.has(g.id)),
];

const entries = groups().flatMap((group) =>
  group.entries
    .filter((entry) => entry.scenario === undefined)
    .map((entry) => [`${group.id}/${entry.id}`, entry] as const),
);

describe("галереи личных раннеров", () => {
  beforeAll(async () => {
    await ensureAdminOpsLocales();
  });
  afterEach(cleanup);

  it("каждое состояние есть в галерее", () => {
    expect(entries.length).toBeGreaterThan(50);
  });

  it.each(["ru", "en"])(
    "язык %s: все записи рисуются без сырых ключей",
    async (lng) => {
      await i18n.changeLanguage(lng);
      for (const [, entry] of entries) {
        const { container, unmount } = render(
          <QueryClientProvider client={new QueryClient()}>
            <MemoryRouter>{entry.render()}</MemoryRouter>
          </QueryClientProvider>,
        );
        // Ключ перевода на экране выглядит как mine.state.online или compile.placement.x.
        expect(container.textContent).not.toMatch(
          /\b(mine|remote|pair|personal|placement|builds|relayError)\.[a-z]+[A-Za-z.]*/,
        );
        unmount();
      }
    },
  );
});
