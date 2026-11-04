import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n, useThemeStore } from "@shared/lib";
import { installViewport } from "@shared/lib/viewport/testing";
import type { SessionUser } from "@entities/session";
import { AccountMenuView } from "./ui/AccountMenuView";

const user: SessionUser = {
  id: "u1",
  name: "Anna Ivanova",
  email: "anna@example.org",
  avatar_initials: "AI",
  is_instance_admin: false,
  email_verified: true,
  locale: "en",
  org_roles: [],
};

const open = async (
  props: Partial<Parameters<typeof AccountMenuView>[0]> = {},
) => {
  render(
    <AccountMenuView
      user={user}
      onOpenSettings={vi.fn()}
      onLogout={vi.fn()}
      {...props}
    />,
  );
  await userEvent.setup().click(screen.getByTestId("account-menu-trigger"));
};

describe("AccountMenuView on a phone", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    useThemeStore.setState({ theme: "dark", lang: "en" });
  });
  afterEach(() => {
    viewport?.restore();
    viewport = undefined;
  });

  it("is a bottom sheet with theme, language, assistant and help", async () => {
    viewport = installViewport(390);
    await open({ onOpenAgent: vi.fn(), onOpenHelp: vi.fn() });
    expect(screen.getByTestId("account-menu")).toHaveAttribute(
      "data-form",
      "sheet",
    );
    expect(screen.getByTestId("account-menu-appearance")).toBeVisible();
    expect(screen.getByTestId("account-menu-agent")).toBeVisible();
    expect(screen.getByTestId("account-menu-help")).toBeVisible();
  });

  it("switches theme and language without leaving the menu", async () => {
    viewport = installViewport(360);
    await open();
    const user_ = userEvent.setup();
    await user_.click(screen.getByTestId("account-menu-theme-light"));
    expect(useThemeStore.getState().theme).toBe("light");
    await user_.click(screen.getByTestId("account-menu-lang-ru"));
    expect(useThemeStore.getState().lang).toBe("ru");
    expect(screen.getByTestId("account-menu")).toBeVisible();
  });

  it("opens the assistant and closes the sheet", async () => {
    viewport = installViewport(390);
    const onOpenAgent = vi.fn();
    await open({ onOpenAgent });
    await userEvent.setup().click(screen.getByTestId("account-menu-agent"));
    expect(onOpenAgent).toHaveBeenCalledOnce();
    expect(screen.queryByTestId("account-menu")).not.toBeInTheDocument();
  });

  it("keeps the desktop menu as it was: no appearance block, no assistant row", async () => {
    viewport = installViewport(1360);
    await open({ onOpenAgent: vi.fn(), onOpenHelp: vi.fn() });
    expect(screen.getByTestId("account-menu")).toHaveAttribute(
      "data-form",
      "popover",
    );
    expect(screen.queryByTestId("account-menu-appearance")).toBeNull();
    expect(screen.queryByTestId("account-menu-agent")).toBeNull();
    expect(screen.queryByTestId("account-menu-help")).toBeNull();
  });
});
