import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n, useThemeStore } from "@shared/lib";
import type { GallerySection } from "@shared/lib/stateGallery";
import { DevSyncStatesPage } from "./DevSyncStatesPage";
import { buildGallerySections } from "./gallerySections";

// Собирает записи сразу, как будто они уже подошли к экрану.
class VisibleObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "";
  readonly scrollMargin = "";
  readonly thresholds: readonly number[] = [];
  constructor(private readonly callback: IntersectionObserverCallback) {}
  observe(target: Element): void {
    this.callback(
      [{ isIntersecting: true, target } as IntersectionObserverEntry],
      this,
    );
  }
  unobserve(): void {
    // не нужно
  }
  disconnect(): void {
    // не нужно
  }
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

const allEntries = (sections: GallerySection[]) =>
  sections.flatMap((section) =>
    section.groups.flatMap((group) => group.entries),
  );

const mount = (
  props: Parameters<typeof DevSyncStatesPage>[0] = {},
  path = "/dev/sync-states",
) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <DevSyncStatesPage {...props} />
    </MemoryRouter>,
  );

describe("галерея состояний синхронизации", () => {
  beforeEach(async () => {
    vi.stubGlobal("IntersectionObserver", VisibleObserver);
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("ни у одной записи нет повторяющегося номера", () => {
    const ids = allEntries(buildGallerySections()).map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("показывает каждое состояние без ошибок в консоли, на русском и английском", async () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {
      // собираем, проверяем ниже
    });
    const warnings = vi.spyOn(console, "warn").mockImplementation(() => {
      // собираем, проверяем ниже
    });
    const entries = allEntries(buildGallerySections());
    const stat = entries.filter((entry) => entry.scenario === undefined);

    for (const language of ["ru", "en"] as const) {
      await i18n.changeLanguage(language);
      const { container, unmount } = mount();
      // Живые записи ждут нажатия «Открыть», остальные собраны.
      expect(container.querySelectorAll("[data-entry]")).toHaveLength(
        entries.length,
      );
      for (const entry of stat) {
        const card = container.querySelector(`[data-entry="${entry.id}"]`);
        expect(card, entry.id).not.toBeNull();
        // Кроме заголовка записи в рамке есть собранное содержимое.
        expect(
          card?.querySelector("header + div")?.childElementCount,
          `${entry.id} (${language})`,
        ).toBeGreaterThan(0);
      }
      unmount();
    }

    expect(errors.mock.calls).toEqual([]);
    expect(warnings.mock.calls).toEqual([]);
    // Больше сотни записей на двух языках: под нагрузкой проходу нужно время.
  }, 60_000);

  it("живые записи без демо только описаны и не открываются", () => {
    mount();
    const buttons = screen.getAllByRole("button", { name: "Открыть" });
    expect(buttons.length).toBeGreaterThan(10);
    for (const button of buttons) expect(button).toBeDisabled();
  });

  it("открывает живую запись по нажатию и ставит демо-сценарий", async () => {
    const user = userEvent.setup();
    const activate = vi.fn();
    const sections: GallerySection[] = [
      {
        id: "demo",
        title: "Демо",
        groups: [
          {
            id: "g",
            title: "Группа",
            entries: [
              {
                id: "live_one",
                title: "Живая",
                scenario: "conflicts",
                render: () => <p>Содержимое живой записи</p>,
              },
              {
                id: "live_two",
                title: "Вторая",
                scenario: "up_to_date",
                render: () => <p>Содержимое второй записи</p>,
              },
            ],
          },
        ],
      },
    ];
    mount({ demo: { activate }, sections });

    const card = (id: string) =>
      document.querySelector<HTMLElement>(`[data-entry="${id}"]`);
    expect(screen.queryByText("Содержимое живой записи")).toBeNull();

    const first = card("live_one");
    if (!first) throw new Error("нет записи");
    await user.click(within(first).getByRole("button", { name: "Открыть" }));
    expect(activate).toHaveBeenLastCalledWith("conflicts");
    expect(screen.getByText("Содержимое живой записи")).toBeInTheDocument();

    // Одновременно открыта одна живая запись: сценарии не смешиваются.
    const second = card("live_two");
    if (!second) throw new Error("нет записи");
    await user.click(within(second).getByRole("button", { name: "Открыть" }));
    expect(activate).toHaveBeenLastCalledWith("up_to_date");
    expect(screen.queryByText("Содержимое живой записи")).toBeNull();
    expect(screen.getByText("Содержимое второй записи")).toBeInTheDocument();
  });

  it("открывает запись из адреса и показывает один раздел", () => {
    const activate = vi.fn();
    mount(
      { demo: { activate } },
      "/dev/sync-states?section=conflicts&open=live_conflicts",
    );
    expect(activate).toHaveBeenCalledWith("conflicts");
    expect(
      document.querySelector('[data-entry="no_remote"]'),
    ).not.toBeInTheDocument();
    expect(
      document.querySelector('[data-entry="live_conflicts"]'),
    ).toBeInTheDocument();
  });

  it("переключает язык и тему", async () => {
    const user = userEvent.setup();
    mount({ sections: [] });
    await user.click(screen.getByRole("button", { name: "EN" }));
    expect(useThemeStore.getState().lang).toBe("en");
    await user.click(screen.getByRole("button", { name: "Светлая" }));
    expect(useThemeStore.getState().theme).toBe("light");
    await user.click(screen.getByRole("button", { name: "RU" }));
    expect(useThemeStore.getState().lang).toBe("ru");
  });
});
