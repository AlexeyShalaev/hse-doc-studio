import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { profileApi, type Profile } from "@entities/profile";
import { i18n } from "@shared/lib/i18n";
import { ProfilePromptDialog } from "./ProfilePromptDialog";

const DEFAULT_PROFILE: Profile = {
  name: null,
  email: null,
  effective_name: "HSE Doc Studio",
  effective_email: "studio@hse-doc-studio.local",
  is_default: true,
  commit_preview: "HSE Doc Studio <studio@hse-doc-studio.local>",
};
const CUSTOM_PROFILE: Profile = {
  name: "Иван",
  email: "i@b.ru",
  effective_name: "Иван",
  effective_email: "i@b.ru",
  is_default: false,
  commit_preview: "Иван <i@b.ru>",
};

const mount = (
  props: Partial<Parameters<typeof ProfilePromptDialog>[0]> = {},
) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ProfilePromptDialog isOpen onClose={onClose} {...props} />
    </QueryClientProvider>,
  );
  return { onClose };
};

describe("ProfilePromptDialog", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("asks to introduce yourself, with a reason-specific explanation", async () => {
    vi.spyOn(profileApi, "get").mockResolvedValue(DEFAULT_PROFILE);
    mount({ reason: "connect" });
    expect(
      await screen.findByRole("dialog", { name: "Представься" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Чтобы подключить репозиторий/),
    ).toBeInTheDocument();
    expect(await screen.findByLabelText("Имя")).toHaveFocus();
  });

  it("saves and hands the profile back so the interrupted action can continue", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "get").mockResolvedValue(DEFAULT_PROFILE);
    vi.spyOn(profileApi, "update").mockResolvedValue(CUSTOM_PROFILE);
    const onSaved = vi.fn();
    mount({ onSaved });
    await user.type(await screen.findByLabelText("Имя"), "Иван");
    await user.type(screen.getByLabelText("E-mail"), "i@b.ru");
    await user.click(
      screen.getByRole("button", { name: "Сохранить и продолжить" }),
    );
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(CUSTOM_PROFILE);
    });
  });

  it("continues straight away when the profile is already set", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "get").mockResolvedValue(CUSTOM_PROFILE);
    const update = vi.spyOn(profileApi, "update");
    const onSaved = vi.fn();
    mount({ onSaved });
    await user.click(
      await screen.findByRole("button", { name: "Сохранить и продолжить" }),
    );
    expect(onSaved).toHaveBeenCalledWith(CUSTOM_PROFILE);
    expect(update).not.toHaveBeenCalled();
  });

  it("closes with Not now", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "get").mockResolvedValue(DEFAULT_PROFILE);
    const { onClose } = mount();
    await user.click(await screen.findByRole("button", { name: "Не сейчас" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders nothing when closed", () => {
    vi.spyOn(profileApi, "get").mockResolvedValue(DEFAULT_PROFILE);
    mount({ isOpen: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
