import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { profileApi, type Profile } from "@entities/profile";
import { ApiError } from "@shared/api";
import { useToastStore } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";
import { AuthorProfileSection } from "./AuthorProfileSection";

const DEFAULT_PROFILE: Profile = {
  name: null,
  email: null,
  effective_name: "HSE Doc Studio",
  effective_email: "studio@hse-doc-studio.local",
  is_default: true,
  commit_preview: "HSE Doc Studio <studio@hse-doc-studio.local>",
};
const CUSTOM_PROFILE: Profile = {
  name: "Алексей Шалаев",
  email: "ashalaev@edu.hse.ru",
  effective_name: "Алексей Шалаев",
  effective_email: "ashalaev@edu.hse.ru",
  is_default: false,
  commit_preview: "Алексей Шалаев <ashalaev@edu.hse.ru>",
};

const mount = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthorProfileSection />
    </QueryClientProvider>,
  );
};

describe("AuthorProfileSection", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    useToastStore.getState().clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows a loading state, then the empty form with the search anchors", async () => {
    vi.spyOn(profileApi, "get").mockResolvedValue(DEFAULT_PROFILE);
    mount();
    expect(screen.getByTestId("profile-loading")).toBeInTheDocument();
    expect(await screen.findByLabelText("Имя")).toBeInTheDocument();
    expect(document.getElementById("profile")).not.toBeNull();
    expect(document.getElementById("profile-name")).not.toBeNull();
    expect(document.getElementById("profile-email")).not.toBeNull();
    expect(
      screen.queryByRole("button", { name: "Вернуть общую подпись" }),
    ).toBeNull();
  });

  it("saves the author and raises a toast", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "get").mockResolvedValue(DEFAULT_PROFILE);
    vi.spyOn(profileApi, "update").mockResolvedValue(CUSTOM_PROFILE);
    mount();
    await user.type(await screen.findByLabelText("Имя"), "Алексей Шалаев");
    await user.type(screen.getByLabelText("E-mail"), "ashalaev@edu.hse.ru");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => {
      expect(useToastStore.getState().toasts.map((x) => x.message)).toContain(
        "Автор сохранён",
      );
    });
    expect(
      await screen.findByRole("button", { name: "Вернуть общую подпись" }),
    ).toBeInTheDocument();
  });

  it("resets to the shared signature after confirmation", async () => {
    const user = userEvent.setup();
    const get = vi.spyOn(profileApi, "get").mockResolvedValue(CUSTOM_PROFILE);
    vi.spyOn(profileApi, "clear").mockResolvedValue(DEFAULT_PROFILE);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    mount();
    expect(await screen.findByLabelText("Имя")).toHaveValue("Алексей Шалаев");
    await user.click(
      screen.getByRole("button", { name: "Вернуть общую подпись" }),
    );
    expect(confirm).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByLabelText("Имя")).toHaveValue("");
    });
    expect(get).toHaveBeenCalled();
    expect(useToastStore.getState().toasts.map((x) => x.message)).toContain(
      "Возвращена общая подпись",
    );
  });

  it("does nothing when the confirmation is declined", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "get").mockResolvedValue(CUSTOM_PROFILE);
    const clear = vi.spyOn(profileApi, "clear");
    vi.spyOn(window, "confirm").mockReturnValue(false);
    mount();
    await user.click(
      await screen.findByRole("button", { name: "Вернуть общую подпись" }),
    );
    expect(clear).not.toHaveBeenCalled();
  });

  it("offers a retry when the profile cannot be loaded", async () => {
    const user = userEvent.setup();
    const get = vi
      .spyOn(profileApi, "get")
      .mockRejectedValueOnce(
        new ApiError("Сервер недоступен", "unknown_error", 500),
      )
      .mockResolvedValue(DEFAULT_PROFILE);
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Сервер недоступен",
    );
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByLabelText("Имя")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });
});
