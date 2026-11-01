import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ShareLink } from "@entities/share-link";
import { i18n } from "@shared/lib";
import { LinkVisitsModal, ShareLinkForm } from "./ShareLinkDialogs";

afterEach(cleanup);
beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

const wrap = (ui: React.ReactNode) =>
  render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);

const LINK: ShareLink = {
  id: "lnk_e",
  label: "Для группы",
  role: "editor",
  show_sources: true,
  require_login: false,
  has_password: true,
  url: "https://s/s/hsl_x",
  token_prefix: "x",
  created_by: null,
  created_at: "2026-11-01T09:00:00Z",
  updated_at: "2026-11-01T09:00:00Z",
  expires_at: null,
  state: "active",
  blocked_reason: null,
  editable: true,
  visits: { visitors: 0, opens: 0, last_at: null },
};

describe("ShareLinkForm", () => {
  it("создание: подпись, роль Читатель, срок 60 дней по умолчанию", async () => {
    const onSubmit = vi.fn();
    wrap(
      <ShareLinkForm
        isOpen
        link={null}
        maxRole="editor"
        forcedLogin={false}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("share-link-sources")).toBeTruthy();
    await userEvent.type(
      screen.getByTestId("share-link-label"),
      "Для научрука",
    );
    await userEvent.click(screen.getByTestId("share-link-submit"));
    expect(onSubmit).toHaveBeenCalledWith({
      mode: "create",
      body: {
        label: "Для научрука",
        role: "reader",
        show_sources: false,
        require_login: false,
        password: null,
        expires_in_days: 60,
      },
    });
  });

  it("пустая подпись и короткий пароль не дают отправить", async () => {
    wrap(
      <ShareLinkForm
        isOpen
        link={null}
        maxRole="editor"
        forcedLogin={false}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const submit = screen.getByTestId<HTMLButtonElement>("share-link-submit");
    expect(submit.disabled).toBe(true);
    await userEvent.type(screen.getByTestId("share-link-label"), "x");
    await userEvent.type(screen.getByTestId("share-link-password"), "short");
    expect(submit.disabled).toBe(true);
  });

  it("принуждённый вход: переключатель включён и неактивен", () => {
    wrap(
      <ShareLinkForm
        isOpen
        link={null}
        maxRole="reviewer"
        forcedLogin
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const toggle = screen.getByTestId("share-link-require-login");
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect((toggle as unknown as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Вход обязателен/)).toBeTruthy();
  });

  it("правка Редактора: предупреждение, снять пароль отправляет только изменения", async () => {
    const onSubmit = vi.fn();
    wrap(
      <ShareLinkForm
        isOpen
        link={LINK}
        maxRole="editor"
        forcedLogin={false}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/Гость сможет менять файлы проекта/)).toBeTruthy();
    expect(screen.queryByTestId("share-link-sources")).toBeNull();
    await userEvent.click(screen.getByTestId("share-link-clear-password"));
    await userEvent.click(screen.getByTestId("share-link-submit"));
    expect(onSubmit).toHaveBeenCalledWith({
      mode: "edit",
      body: {
        label: null,
        role: null,
        show_sources: null,
        require_login: null,
        password: null,
        clear_password: true,
        expires_in_days: null,
        clear_expiry: false,
      },
    });
  });
});

describe("LinkVisitsModal", () => {
  it("таблица переходов и пусто", () => {
    const { unmount } = wrap(
      <LinkVisitsModal
        link={LINK}
        status="ready"
        items={[
          {
            visitor_kind: "guest",
            name: "Пётр",
            first_at: "2026-11-01T13:50:00Z",
            last_at: "2026-11-01T14:02:00Z",
            opens: 3,
          },
        ]}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("Гость: Пётр")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Открытий" })).toBeTruthy();
    unmount();
    wrap(
      <LinkVisitsModal
        link={LINK}
        status="ready"
        items={[]}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("Переходов пока не было")).toBeTruthy();
  });
});
