import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ShareLink, ShareLinkList } from "@entities/share-link";
import { i18n } from "@shared/lib";
import { ShareLinksView, type ShareLinksViewProps } from "./ShareLinksView";

afterEach(cleanup);
beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

const READER: ShareLink = {
  id: "lnk_r",
  label: "Для научрука",
  role: "reader",
  show_sources: false,
  require_login: false,
  has_password: false,
  url: "https://studio.example.org/s/hsl_reader",
  token_prefix: "reader00",
  created_by: { id: "u1", name: "Анна Петрова" },
  created_at: "2026-11-01T09:00:00Z",
  updated_at: "2026-11-01T09:00:00Z",
  expires_at: "2026-12-31T00:00:00Z",
  state: "active",
  blocked_reason: null,
  editable: true,
  visits: { visitors: 1, opens: 3, last_at: "2026-11-01T14:02:00Z" },
};
const EDITOR: ShareLink = {
  ...READER,
  id: "lnk_e",
  label: "Для группы",
  role: "editor",
  show_sources: true,
  has_password: true,
  require_login: true,
  expires_at: null,
  visits: { visitors: 0, opens: 0, last_at: null },
};

const list = (
  items: ShareLink[],
  extra: Partial<ShareLinkList> = {},
): ShareLinkList => ({
  items,
  can_create: true,
  max_role: "editor",
  forced_login: false,
  revoked_count: 0,
  ...extra,
});

const mount = (extra: Partial<ShareLinksViewProps> = {}) => {
  const props: ShareLinksViewProps = {
    status: "ready",
    list: list([READER, EDITOR]),
    showRevoked: false,
    onToggleRevoked: vi.fn(),
    onCreate: vi.fn(),
    onEdit: vi.fn(),
    onRotate: vi.fn(),
    onRevoke: vi.fn(),
    onVisits: vi.fn(),
    now: Date.parse("2026-11-01T16:00:00Z"),
    ...extra,
  };
  render(
    <I18nextProvider i18n={i18n}>
      <ShareLinksView {...props} />
    </I18nextProvider>,
  );
  return props;
};

describe("ShareLinksView", () => {
  it("строки ссылок с чипами, адресом и переходами", () => {
    mount();
    const row = screen.getByTestId("share-link-row-lnk_r");
    expect(row.dataset.state).toBe("active");
    expect(within(row).getByText("Читатель")).toBeTruthy();
    expect(within(row).getByText("до 31.12.2026")).toBeTruthy();
    expect(within(row).getByText(/3 перехода, 1 человек/)).toBeTruthy();
    expect(
      within(screen.getByTestId("share-link-url-lnk_r")).getByDisplayValue(
        READER.url ?? "",
      ),
    ).toBeTruthy();
    const editor = screen.getByTestId("share-link-row-lnk_e");
    expect(within(editor).getByText("Нужен вход")).toBeTruthy();
    expect(within(editor).getByText("Пароль")).toBeTruthy();
    expect(within(editor).getByText("Переходов пока не было")).toBeTruthy();
  });

  it("клик по переходам и кнопка создания", async () => {
    const props = mount();
    await userEvent.click(screen.getByTestId("share-link-visits-open-lnk_r"));
    expect(props.onVisits).toHaveBeenCalledWith(READER);
    await userEvent.click(screen.getByTestId("share-link-create"));
    expect(props.onCreate).toHaveBeenCalledTimes(1);
  });

  it("пусто: подсказка, что проект видят только участники", () => {
    mount({ list: list([]) });
    expect(screen.getByTestId("share-links-empty").textContent).toContain(
      "Ссылок нет",
    );
  });

  it("политика запретила ссылки: создать нельзя, строка помечена", () => {
    mount({
      list: list(
        [{ ...READER, state: "blocked", blocked_reason: "org_links_off" }],
        { can_create: false },
      ),
    });
    expect(
      screen.getByTestId<HTMLButtonElement>("share-link-create").disabled,
    ).toBe(true);
    expect(screen.getByTestId("share-link-row-lnk_r").dataset.state).toBe(
      "blocked",
    );
    expect(
      screen.getByText("Не действует: организация запретила ссылки"),
    ).toBeTruthy();
  });

  it("истекшая ссылка без адреса, отозванные под переключателем", async () => {
    const props = mount({
      list: list(
        [
          { ...READER, state: "expired", url: null },
          {
            ...EDITOR,
            id: "lnk_old",
            state: "revoked",
            url: null,
            editable: false,
          },
        ],
        { revoked_count: 1 },
      ),
    });
    expect(screen.queryByTestId("share-link-url-lnk_r")).toBeNull();
    expect(screen.queryByTestId("share-link-row-lnk_old")).toBeNull();
    await userEvent.click(screen.getByTestId("share-links-revoked-toggle"));
    expect(props.onToggleRevoked).toHaveBeenCalled();
  });

  it("NDA: пояснение про обязательный вход", () => {
    mount({ list: list([READER], { forced_login: true }) });
    expect(screen.getByText(/Политика требует вход/)).toBeTruthy();
  });

  it("загрузка и ошибка", () => {
    mount({ status: "error", list: null, onRetry: vi.fn() });
    expect(screen.getByText("Не удалось загрузить ссылки")).toBeTruthy();
  });
});
