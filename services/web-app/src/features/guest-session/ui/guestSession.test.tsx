import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { GuestBadgeView } from "./GuestBadge";
import { GuestProjectsView } from "./GuestHome";
import { LinkAccessBanner } from "./LinkAccessBanner";
import { LinkRevokedScreen } from "./LinkRevokedScreen";

afterEach(cleanup);
beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

const wrap = (ui: React.ReactNode) =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{ui}</MemoryRouter>
    </I18nextProvider>,
  );

const GUEST = {
  name: "Борис",
  links: [
    {
      project_id: "p1",
      project_name: "ВКР",
      link_label: "Для группы",
      role: "editor" as const,
      show_sources: true,
    },
    {
      project_id: "p2",
      project_name: "Курсовая",
      link_label: "Для научрука",
      role: "reader" as const,
      show_sources: false,
    },
  ],
};

describe("гость по ссылке", () => {
  it("бейдж и меню: сменить имя, войти, выйти", async () => {
    const onRename = vi.fn();
    const onLeave = vi.fn();
    const onSignIn = vi.fn();
    wrap(
      <GuestBadgeView
        guest={GUEST}
        onRename={onRename}
        onSignIn={onSignIn}
        onLeave={onLeave}
      />,
    );
    expect(screen.getByTestId("guest-badge").textContent).toContain(
      "Гость: Борис",
    );
    await userEvent.click(screen.getByTestId("guest-badge"));
    expect(screen.getByTestId("guest-menu")).toBeTruthy();
    await userEvent.click(screen.getByTestId("guest-leave"));
    expect(onLeave).toHaveBeenCalled();
  });

  it("проекты гостя: читатель без исходников ведёт на просмотр PDF", () => {
    wrap(<GuestProjectsView guest={GUEST} />);
    expect(
      screen.getByTestId("guest-project-open-p1").getAttribute("href"),
    ).toBe("/projects/p1");
    expect(
      screen.getByTestId("guest-project-open-p2").getAttribute("href"),
    ).toBe("/projects/p2/view");
  });

  it("баннер называет ссылку, доступное и недоступное", () => {
    wrap(
      <LinkAccessBanner label="Для группы" role="editor" showSources guest />,
    );
    expect(screen.getByTestId("link-access-banner").textContent).toContain(
      "Вы открыли проект по ссылке «Для группы». Доступно: правка. Недоступно: агент, сдача, подписи, git.",
    );
  });

  it("экран отозванной ссылки", () => {
    wrap(<LinkRevokedScreen />);
    expect(screen.getByRole("alert").textContent).toContain(
      "Ссылка больше не действует",
    );
  });
});
