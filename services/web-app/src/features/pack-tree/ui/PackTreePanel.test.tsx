import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { PackTreeSchema, packStudioApi } from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { PackTreePanel } from "./PackTreePanel";

const TREE = PackTreeSchema.parse(
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../../../../contracts/pack-studio/fixtures/PackTree/monorepo.json",
      ),
      "utf8",
    ),
  ),
);
const BASE = "hse-cs-sse/templates/coursework";

const mount = (selectedPath: string | null = null) => {
  const onSelect = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PackTreePanel
        workspaceId="ws1"
        selectedPath={selectedPath}
        onSelect={onSelect}
      />
    </QueryClientProvider>,
  );
  return onSelect;
};

describe("дерево пространства", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("версии со статусом и замком у выпущенной, путь к открытому файлу раскрыт", async () => {
    vi.spyOn(packStudioApi, "tree").mockResolvedValue({
      ...TREE,
      files: [
        ...TREE.files,
        {
          path: `${BASE}/versions/2026.1.6/files/logo.png`,
          is_dir: false,
          size: 10,
          read_only: null,
        },
      ],
    });
    const onSelect = mount(`${BASE}/versions/2026.1.6/version.yaml`);
    expect(
      await screen.findByTestId("tree-released-2026.1.5"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("tree-released-2026.1.6"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("МИЭМ, Системная и программная инженерия"),
    ).toBeInTheDocument();

    const manifest = screen.getByTestId(
      `tree-file-${BASE}/versions/2026.1.6/version.yaml`,
    );
    expect(manifest.closest("[role=treeitem]")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await userEvent.click(manifest);
    expect(onSelect).toHaveBeenCalledWith(
      `${BASE}/versions/2026.1.6/version.yaml`,
    );

    // Картинка в редакторе не открывается.
    await userEvent.click(
      screen.getByTestId(`tree-dir-${BASE}/versions/2026.1.6/files`),
    );
    expect(
      screen.getByTestId(`tree-file-${BASE}/versions/2026.1.6/files/logo.png`),
    ).toBeDisabled();
  });

  it("папка сворачивается и раскрывается по нажатию", async () => {
    vi.spyOn(packStudioApi, "tree").mockResolvedValue(TREE);
    mount();
    const pack = await screen.findByTestId("tree-dir-hse-cs-sse");
    expect(
      screen.getByTestId("tree-file-hse-cs-sse/pack.yaml"),
    ).toBeInTheDocument();
    await userEvent.click(pack);
    expect(
      screen.queryByTestId("tree-file-hse-cs-sse/pack.yaml"),
    ).not.toBeInTheDocument();
    await userEvent.click(pack);
    expect(
      screen.getByTestId("tree-file-hse-cs-sse/pack.yaml"),
    ).toBeInTheDocument();
  });
});
