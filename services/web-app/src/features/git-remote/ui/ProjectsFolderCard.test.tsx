import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { ProjectsFolderCard } from "./ProjectsFolderCard";

const caps = vi.hoisted(() => ({ lacking: new Set<string>() }));
vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useCapabilities: () => ({
    has: (name: string) => !caps.lacking.has(name),
    lacks: (name: string) => caps.lacking.has(name),
  }),
}));

const SETTINGS = {
  theme: "system",
  default_engine: "xelatex",
  latex_passes: 3,
  latex_flags: null,
  compile_image: null,
  default_ai_provider_id: null,
  default_ai_model: null,
  agent_auto_approve_writes: false,
};

const mount = (projectsDir: string | null) => {
  vi.spyOn(apiClient, "get").mockResolvedValue({
    data: { ...SETTINGS, projects_dir: projectsDir },
  });
  const put = vi.spyOn(apiClient, "put").mockImplementation((_url, body) =>
    Promise.resolve({
      data: {
        ...SETTINGS,
        projects_dir: (body as { projects_dir: string | null }).projects_dir,
      },
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ProjectsFolderCard />
    </QueryClientProvider>,
  );
  return put;
};

describe("ProjectsFolderCard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    caps.lacking = new Set();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("saves the folder for cloud projects", async () => {
    const user = userEvent.setup();
    const put = mount(null);
    const input = await screen.findByTestId("projects-dir-input");
    await waitFor(() => {
      expect(input).toBeEnabled();
    });
    expect(screen.getByTestId("projects-dir-save")).toBeDisabled();
    await user.type(input, "/Users/anna/Студия/облако");
    await user.click(screen.getByTestId("projects-dir-save"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledWith("/settings", {
        projects_dir: "/Users/anna/Студия/облако",
      });
    });
  });

  it("brings the standard folder back with one button", async () => {
    const user = userEvent.setup();
    const put = mount("/Users/anna/work");
    expect(await screen.findByDisplayValue("/Users/anna/work")).toBeVisible();
    await user.click(screen.getByTestId("projects-dir-reset"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledWith("/settings", { projects_dir: null });
    });
  });

  it("is absent on a server", () => {
    caps.lacking = new Set(["git_server_login"]);
    mount(null);
    expect(screen.queryByTestId("projects-dir-input")).toBeNull();
  });
});
