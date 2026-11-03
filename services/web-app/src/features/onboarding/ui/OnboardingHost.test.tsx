import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { LOCAL_BOOTSTRAP, sessionKeys } from "@entities/session";
import type { OnboardingState } from "@entities/onboarding";
import { useOnboardingStore } from "../model/onboardingStore";
import { AUTOSTART_FLAG, INVITE_DISMISSED_KEY } from "../lib/autostart";
import { OnboardingHost } from "./OnboardingHost";

const STATE: OnboardingState = {
  status: "pending",
  scenario_version: 0,
  step: null,
  answers: {},
  started_at: null,
  finished_at: null,
  updated_at: null,
};

// Сохранения идут очередью промисов: под нагрузкой CI секунды по умолчанию мало.
const WAIT = { timeout: 4000 };

const Where = () => <span data-testid="where">{useLocation().pathname}</span>;

const mount = (state: OnboardingState) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), LOCAL_BOOTSTRAP);
  vi.spyOn(apiClient, "get").mockImplementation((url: string) => {
    if (url === "/onboarding") return Promise.resolve({ data: state });
    if (url === "/catalog/packs") return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
  const patch = vi
    .spyOn(apiClient, "patch")
    .mockImplementation((_url: string, body: unknown) =>
      Promise.resolve({ data: { ...state, ...(body as object) } }),
    );
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Where />
        <Routes>
          <Route path="*" element={<OnboardingHost />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { patch };
};

describe("OnboardingHost", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    window.localStorage.setItem(AUTOSTART_FLAG, "on");
    window.localStorage.removeItem(INVITE_DISMISSED_KEY);
    useOnboardingStore.getState().close();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("новичку открывает знакомство сам, пропуск сохраняет skipped", async () => {
    const user = userEvent.setup();
    const { patch } = mount(STATE);

    await user.click(await screen.findByTestId("onboarding-skip", {}, WAIT));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith(
        "/onboarding",
        expect.objectContaining({ status: "skipped", step: "" }),
        expect.anything(),
      );
    }, WAIT);
    expect(useOnboardingStore.getState().phase).toBe("idle");
  });

  it("анкета: ответы сохраняются, после неё экскурсия по главной", async () => {
    const user = userEvent.setup();
    const { patch } = mount(STATE);

    await user.click(await screen.findByTestId("onboarding-start"));
    await user.click(screen.getByTestId("onboarding-answer-role-admin"));
    await user.click(screen.getByTestId("onboarding-answer-latex-none"));
    await user.click(screen.getByTestId("onboarding-answer-git-pro"));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith(
        "/onboarding",
        expect.objectContaining({
          answers: { role: "admin", latex: "none", git: "pro" },
        }),
        expect.anything(),
      );
    }, WAIT);
    expect(useOnboardingStore.getState().phase).toBe("interface");
    expect(await screen.findByTestId("tour-overlay")).toHaveAttribute(
      "data-tour-step",
      "home.new-project",
    );
  });

  it("давнему пользователю только приглашение, «Не сейчас» его прячет", async () => {
    const user = userEvent.setup();
    mount({ ...STATE, status: "suggested" });

    const invite = await screen.findByTestId("onboarding-invite");
    expect(screen.queryByTestId("onboarding-intro")).toBeNull();
    const [later] = within(invite).getAllByRole("button", {
      name: "Не сейчас",
    });
    if (!later) throw new Error("нет кнопки");
    await user.click(later);

    expect(screen.queryByTestId("onboarding-invite")).toBeNull();
    expect(window.localStorage.getItem(INVITE_DISMISSED_KEY)).not.toBeNull();
  });
});
