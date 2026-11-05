import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { i18n, useStaleBuildStore } from "@shared/lib";
import { StaleBuildBanner } from "./StaleBuildBanner";

const reload = vi.fn();

const mount = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <StaleBuildBanner />
    </I18nextProvider>,
  );

beforeEach(async () => {
  reload.mockReset();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      reload,
      pathname: "/",
      search: "",
      hash: "",
      href: "http://localhost/",
    },
  });
  useStaleBuildStore.setState({ reason: null, screenShown: false });
  await i18n.changeLanguage("ru");
});

describe("StaleBuildBanner", () => {
  it("без устаревшей сборки не виден", () => {
    mount();
    expect(screen.queryByTestId("stale-build-banner")).toBeNull();
  });

  it("показывает сообщение и по кнопке обновляет страницу", async () => {
    useStaleBuildStore.setState({ reason: "version" });
    mount();
    expect(screen.getByRole("status").textContent).toContain("новая версия");
    await userEvent.click(screen.getByTestId("stale-build-refresh"));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("говорит по-английски при языке en", async () => {
    await i18n.changeLanguage("en");
    useStaleBuildStore.setState({ reason: "chunk" });
    mount();
    expect(screen.getByRole("status").textContent).toContain("new version");
    expect(screen.getByTestId("stale-build-refresh").textContent).toBe(
      "Refresh",
    );
  });

  it("скрыт, когда экран ошибки уже объяснил то же самое", () => {
    useStaleBuildStore.setState({ reason: "chunk", screenShown: true });
    mount();
    expect(screen.queryByTestId("stale-build-banner")).toBeNull();
  });
});
