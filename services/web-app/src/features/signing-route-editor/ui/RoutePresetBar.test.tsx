import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { RoutePreset } from "@entities/signing-route";
import { RoutePresetBar } from "./RoutePresetBar";

// Шапка редактора маршрута (docs/design/signing-route.md, 15.7): строка «В новой версии шаблона
// другой маршрут этой точки», когда состав собран по пресету другой версии (`base_version`).

const PRESET: RoutePreset = {
  version: "2026.1.5",
  base_version: "2026.1.5",
  steps: [["author"], ["supervisor"]],
  extra_slots: [],
  optional: [],
  skipped_by_condition: [],
  differs: [],
};

const mount = (preset: Partial<RoutePreset>) => {
  const onRestore = vi.fn(() => Promise.resolve());
  render(
    <I18nextProvider i18n={i18n}>
      <RoutePresetBar
        preset={{ ...PRESET, ...preset }}
        busy={false}
        pending={false}
        onRestore={onRestore}
      />
    </I18nextProvider>,
  );
  return { onRestore };
};

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

afterEach(() => {
  cleanup();
});

describe("шапка маршрута из шаблона: новая версия шаблона", () => {
  it("состав по прежней версии, пресет новой другой: строка о новой версии и «Вернуть как в шаблоне»", async () => {
    const { onRestore } = mount({
      base_version: "2026.1.4",
      differs: ["slots", "optional"],
    });
    const bar = screen.getByTestId("route-preset");
    expect(bar).toHaveAttribute("data-new-version");
    const mark = screen.getByTestId("route-preset-mark");
    expect(mark).toHaveTextContent(
      "В новой версии шаблона другой маршрут этой точки",
    );
    expect(mark).toHaveAttribute(
      "title",
      "Шаблон 2026.1.5 задаёт этой точке другой маршрут, отличается: подписи сверх точки, отметки «необязательна»",
    );
    expect(bar).not.toHaveTextContent("Изменён вами");
    expect(bar).toHaveTextContent(
      "отличается: подписи сверх точки, отметки «необязательна»",
    );
    const user = userEvent.setup();
    await user.click(within(bar).getByTestId("route-preset-reset"));
    await user.click(await screen.findByTestId("route-preset-confirm"));
    expect(onRestore).toHaveBeenCalledTimes(1);
  });

  it("состав не по пресету (base_version null) и отличается: тоже новая версия", () => {
    mount({ base_version: null, differs: ["order"] });
    expect(screen.getByTestId("route-preset-mark")).toHaveTextContent(
      "В новой версии шаблона другой маршрут этой точки",
    );
  });

  it("та же версия и отличается: «Изменён вами», строки о новой версии нет", () => {
    mount({ differs: ["order"] });
    const bar = screen.getByTestId("route-preset");
    expect(bar).not.toHaveAttribute("data-new-version");
    expect(screen.getByTestId("route-preset-mark")).toHaveTextContent(
      "Изменён вами",
    );
    expect(bar).not.toHaveTextContent("В новой версии шаблона");
  });

  it("другая версия, но состав как в шаблоне: «Маршрут из шаблона» без кнопки", () => {
    mount({ base_version: "2026.1.4", differs: [] });
    const bar = screen.getByTestId("route-preset");
    expect(bar).not.toHaveAttribute("data-new-version");
    expect(screen.getByTestId("route-preset-mark")).toHaveTextContent(
      "Маршрут из шаблона",
    );
    expect(within(bar).queryByTestId("route-preset-reset")).toBeNull();
  });

  it("en: The new template version has a different route for this checkpoint", async () => {
    await i18n.changeLanguage("en");
    mount({ base_version: "2026.1.4", differs: ["slots"] });
    expect(screen.getByTestId("route-preset-mark")).toHaveTextContent(
      "The new template version has a different route for this checkpoint",
    );
    expect(screen.getByTestId("route-preset-reset")).toHaveTextContent(
      "Reset to template",
    );
  });
});
