import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib";
import { LocalStudioGuide, OpenInLocalStudio } from "./index";

const ID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b";
const INFO = {
  server_url: "https://hse-doc-studio.ai-ops.ru",
  server_version: "0.3.0",
  git_remote_enabled: true,
  recommended_tag: "0.3",
  image: "ghcr.io/alexeyshalaev/hse-doc-studio",
  install_base_url:
    "https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy",
  releases_url: "https://github.com/AlexeyShalaev/hse-doc-studio/releases",
  default_port: 17240,
};

const mount = (ui: React.ReactNode, info: object = INFO) => {
  vi.spyOn(apiClient, "get").mockImplementation((url: string) =>
    url === "/local-studio"
      ? Promise.resolve({ data: info })
      : Promise.reject(new Error(`unexpected ${url}`)),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>{ui}</MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
};

describe("LocalStudioGuide", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fills this server into the install command and copies it", async () => {
    const user = userEvent.setup();
    mount(<LocalStudioGuide />);
    const block = await screen.findByTestId("local-studio-install-command");
    const field = within(block).getByLabelText("Команда установки");
    expect((field as HTMLTextAreaElement).value).toContain(
      "HSE_STUDIO_CONNECT='https://hse-doc-studio.ai-ops.ru'",
    );
    await user.click(within(block).getByRole("button", { name: "Копировать" }));
    expect(await navigator.clipboard.readText()).toBe(
      (field as HTMLTextAreaElement).value,
    );
  });

  it("switches the command by OS and pins the server version on request", async () => {
    const user = userEvent.setup();
    mount(<LocalStudioGuide />);
    await user.click(await screen.findByTestId("local-studio-os-windows"));
    const field = within(
      screen.getByTestId("local-studio-install-command"),
    ).getByLabelText<HTMLTextAreaElement>("Команда установки");
    expect(field.value).toMatch(
      /^\$env:HSE_STUDIO_LANG='ru'; .*install\.ps1 \| iex$/,
    );
    await user.click(screen.getByTestId("local-studio-pin"));
    expect(field.value).toContain("$env:TAG='0.3'");
  });

  it("leads the connect button to the local Studio on the chosen port", async () => {
    const user = userEvent.setup();
    mount(<LocalStudioGuide projectId={ID} />);
    const port = await screen.findByTestId("local-studio-port");
    await user.clear(port);
    await user.type(port, "17245");
    const links = screen.getAllByTestId("open-in-local-studio");
    const hrefs = links.map((link) => new URL(link.getAttribute("href") ?? ""));
    expect(hrefs.map((url) => url.origin)).toEqual([
      "http://localhost:17245",
      "http://localhost:17245",
    ]);
    expect(hrefs[1]?.searchParams.get("project")).toBe(ID);
    expect(hrefs[0]?.searchParams.get("server")).toBe(INFO.server_url);
    expect(window.localStorage.getItem("hse-studio.local-studio.port")).toBe(
      "17245",
    );
  });

  it("warns and offers no connect button when git is off on the server", async () => {
    mount(<LocalStudioGuide />, { ...INFO, git_remote_enabled: false });
    expect(await screen.findByText(/Администратор выключил git/)).toBeVisible();
    expect(
      screen.queryByTestId("open-in-local-studio"),
    ).not.toBeInTheDocument();
  });

  it("speaks English with an English interface", async () => {
    await i18n.changeLanguage("en");
    mount(<OpenInLocalStudio projectId={ID} />);
    expect(
      await screen.findByRole("link", { name: /Open in the local Studio/ }),
    ).toBeVisible();
  });
});
