import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ShareLinkPreview } from "@entities/share-link";
import { i18n } from "@shared/lib";
import { ShareLinkView, type ShareLinkViewProps } from "./ShareLinkView";

afterEach(cleanup);
beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

const OK: ShareLinkPreview = {
  state: "ok",
  project_name: "ВКР: Анализ требований",
  owner_name: "Анна Петрова",
  role: "reader",
  show_sources: false,
  guest_name_required: false,
  signed_in: false,
};

const mount = (extra: Partial<ShareLinkViewProps>) => {
  const onOpen = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <ShareLinkView
          status="ready"
          preview={OK}
          onOpen={onOpen}
          loginHref="/login?next=x"
          {...extra}
        />
      </MemoryRouter>
    </I18nextProvider>,
  );
  return onOpen;
};

const state = () => screen.getByTestId("share-link-page").dataset.state;

describe("страница ссылки", () => {
  it("читатель: проект и роль словами, без поля имени", async () => {
    const onOpen = mount({});
    expect(state()).toBe("ok");
    expect(
      screen.getByText("Анна Петрова открыл(а) вам «ВКР: Анализ требований»"),
    ).toBeTruthy();
    expect(screen.getByText("Просмотр PDF")).toBeTruthy();
    expect(screen.queryByTestId("share-link-guest-name")).toBeNull();
    await userEvent.click(screen.getByTestId("share-link-open"));
    expect(onOpen).toHaveBeenCalledWith({ password: null, guestName: null });
  });

  it("редактор: имя обязательно", async () => {
    const onOpen = mount({
      preview: {
        ...OK,
        role: "editor",
        show_sources: true,
        guest_name_required: true,
      },
    });
    const open = screen.getByTestId<HTMLButtonElement>("share-link-open");
    expect(open.disabled).toBe(true);
    await userEvent.type(screen.getByTestId("share-link-guest-name"), "Борис");
    await userEvent.click(open);
    expect(onOpen).toHaveBeenCalledWith({ password: null, guestName: "Борис" });
  });

  it("вошедший: «Вы войдёте как» вместо имени", () => {
    mount({
      preview: { ...OK, signed_in: true },
      signedInName: "Вера Смирнова",
    });
    expect(screen.getByText("Вы войдёте как Вера Смирнова")).toBeTruthy();
  });

  it("пароль: ни проекта, ни роли до ввода; ошибка видна", async () => {
    const hidden = {
      ...OK,
      state: "password_required" as const,
      project_name: null,
      owner_name: null,
      role: null,
    };
    const onOpen = mount({ preview: hidden, error: "Неверный пароль" });
    expect(state()).toBe("password_required");
    expect(screen.queryByText(/ВКР/)).toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("Неверный пароль");
    await userEvent.type(
      screen.getByTestId("share-link-password-input"),
      "password1",
    );
    await userEvent.click(screen.getByTestId("share-link-open"));
    expect(onOpen).toHaveBeenCalledWith({
      password: "password1",
      guestName: null,
    });
  });

  it("нужен вход и только организация ведут на вход с возвратом", () => {
    mount({ preview: { ...OK, state: "login_required" } });
    expect(screen.getByTestId("share-link-login").getAttribute("href")).toBe(
      "/login?next=x",
    );
    cleanup();
    mount({ preview: { ...OK, state: "org_only", owner_name: "МСПИН 2025" } });
    expect(
      screen.getByText(/только для участников организации МСПИН 2025/),
    ).toBeTruthy();
  });

  it("недействующая ссылка", () => {
    mount({ status: "error", preview: OK });
    expect(state()).toBe("inactive");
    expect(screen.getByText(/Ссылка не действует/)).toBeTruthy();
  });
});
