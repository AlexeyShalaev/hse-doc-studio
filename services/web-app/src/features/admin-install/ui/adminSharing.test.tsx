import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AdminSharingSettings } from "@entities/share-link";
import { i18n } from "@shared/lib";
import { AdminSharingSettingsView } from "./AdminSharingSettings";

afterEach(cleanup);
beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

const SETTINGS: AdminSharingSettings = {
  links_enabled: true,
  max_link_role: "editor",
  project_invites_allow_signup: true,
  fields: {
    "sharing.links_enabled": { source: "default", locked: false },
    "sharing.max_link_role": { source: "default", locked: false },
    "registration.project_invites_allow_signup": {
      source: "env",
      locked: true,
    },
  },
};

describe("админка: общий доступ", () => {
  it("выключение ссылок отправляет только изменённый ключ; заданное окружением заблокировано", async () => {
    const onSave = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <AdminSharingSettingsView settings={SETTINGS} onSave={onSave} />
      </I18nextProvider>,
    );
    expect(
      screen.getByTestId<HTMLButtonElement>("admin-sharing-invite-signup")
        .disabled,
    ).toBe(true);
    await userEvent.click(screen.getByTestId("admin-sharing-links-toggle"));
    await userEvent.click(screen.getByTestId("admin-sharing-save"));
    expect(onSave).toHaveBeenCalledWith({
      links_enabled: false,
      max_link_role: null,
      project_invites_allow_signup: null,
    });
  });
});
