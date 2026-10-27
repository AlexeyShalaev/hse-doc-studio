import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, getCsrfToken, setCsrfToken } from "@shared/api";
import { i18n } from "@shared/lib";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import { AccountMenu } from "./index";

const serverUser = JSON.parse(
  readFileSync(
    join(
      import.meta.dirname,
      "../../../../..",
      "contracts/server/fixtures/Bootstrap/server_user.json",
    ),
    "utf8",
  ),
) as Bootstrap;

const mount = (bootstrap: Bootstrap) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <AccountMenu />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
  return client;
};

describe("AccountMenu", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    setCsrfToken(null);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("is absent in local mode and sends no requests", () => {
    const get = vi.spyOn(apiClient, "get");
    const post = vi.spyOn(apiClient, "post");
    mount(LOCAL_BOOTSTRAP);
    expect(
      screen.queryByTestId("account-menu-trigger"),
    ).not.toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
  });

  it("is absent for an anonymous visitor in server mode", () => {
    mount({ ...serverUser, user: null });
    expect(
      screen.queryByTestId("account-menu-trigger"),
    ).not.toBeInTheDocument();
  });

  it("shows who is signed in", async () => {
    const user = userEvent.setup();
    mount(serverUser);
    await user.click(screen.getByTestId("account-menu-trigger"));
    expect(await screen.findByTestId("account-menu")).toHaveTextContent(
      serverUser.user?.email ?? "",
    );
    expect(screen.getByTestId("account-menu-logout")).toHaveTextContent(
      "Выйти",
    );
  });

  it("logout drops every cached query of the user and the CSRF token", async () => {
    const user = userEvent.setup();
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: undefined, status: 204 });
    const client = mount(serverUser);
    setCsrfToken("tok");
    client.setQueryData(["projects", "list"], [{ id: "p1", name: "Чужой" }]);
    client.setQueryData(["chats", "p1"], ["secret"]);

    await user.click(screen.getByTestId("account-menu-trigger"));
    await user.click(await screen.findByTestId("account-menu-logout"));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/auth/logout",
        undefined,
        expect.anything(),
      );
    });
    await waitFor(() => {
      expect(client.getQueryData(["projects", "list"])).toBeUndefined();
    });
    expect(client.getQueryData(["chats", "p1"])).toBeUndefined();
    expect(getCsrfToken()).toBeNull();
    expect(client.getQueryState(sessionKeys.bootstrap())?.isInvalidated).toBe(
      true,
    );
  });

  it("keeps the cache when the server did not confirm the logout", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "post").mockRejectedValue(new Error("offline"));
    const client = mount(serverUser);
    setCsrfToken("tok");
    client.setQueryData(["projects", "list"], ["mine"]);

    await user.click(screen.getByTestId("account-menu-trigger"));
    await user.click(await screen.findByTestId("account-menu-logout"));

    await waitFor(() => {
      expect(screen.getByTestId("account-menu-logout")).not.toBeDisabled();
    });
    expect(client.getQueryData(["projects", "list"])).toEqual(["mine"]);
    expect(getCsrfToken()).toBe("tok");
  });
});
