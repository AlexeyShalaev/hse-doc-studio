import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  CatalogApplySchema,
  CatalogCheckSchema,
  WorkspaceCatalogSchema,
  packCatalogApi,
} from "@entities/pack-catalog";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { ConnectCatalogDialog } from "./ConnectCatalogDialog";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-catalog/fixtures",
);
const load = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));

const NONE = WorkspaceCatalogSchema.parse(load("WorkspaceCatalog", "none"));
const CONNECTED = WorkspaceCatalogSchema.parse(
  load("WorkspaceCatalog", "connected"),
);
const BLOCKED = CatalogCheckSchema.parse(load("CatalogCheck", "blocked"));
const OK = CatalogCheckSchema.parse(load("CatalogCheck", "ok"));
const APPLIED = CatalogApplySchema.parse(load("CatalogApply", "applied"));
const WS = "3c2b1a09-8f7e-4d6c-9b5a-493827161504";

const mount = (onClose = vi.fn()) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ConnectCatalogDialog workspaceId={WS} isOpen onClose={onClose} />
    </QueryClientProvider>,
  );

describe("«Подключить к каталогу этой Студии»", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("не подключена: проверка, пояснение про встроенный пак, повтор с заменой, применение", async () => {
    vi.spyOn(packCatalogApi, "workspace").mockResolvedValue(NONE);
    const check = vi
      .spyOn(packCatalogApi, "checkWorkspace")
      .mockResolvedValueOnce(BLOCKED)
      .mockResolvedValueOnce(OK);
    const apply = vi
      .spyOn(packCatalogApi, "applyWorkspace")
      .mockResolvedValue(APPLIED);
    mount();
    expect(await screen.findByTestId("ws-catalog-none")).toBeInTheDocument();
    expect(screen.queryByTestId("ws-catalog-toggle")).toBeNull();

    await userEvent.click(screen.getByTestId("ws-catalog-check"));
    expect(check).toHaveBeenLastCalledWith(WS, false);
    expect(
      await screen.findByText(
        /отметьте «Заменить встроенный» и проверьте снова/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("ws-catalog-apply")).toBeDisabled();

    await userEvent.click(screen.getByTestId("ws-catalog-replace"));
    await userEvent.click(screen.getByTestId("ws-catalog-check"));
    expect(check).toHaveBeenLastCalledWith(WS, true);
    await waitFor(() => {
      expect(screen.getByTestId("ws-catalog-apply")).toBeEnabled();
    });
    await userEvent.click(screen.getByTestId("ws-catalog-apply"));
    expect(apply).toHaveBeenCalledWith(WS, OK.revision);
    expect(
      await screen.findByTestId("catalog-apply-result"),
    ).toBeInTheDocument();
  });

  it("подключена: состояние, выключение и отключение с подтверждением", async () => {
    const off = {
      source: CONNECTED.source ? { ...CONNECTED.source, enabled: false } : null,
    };
    // Сервер: подключена, после «Выключить» выключена, после «Отключить» не подключена.
    let current = CONNECTED;
    vi.spyOn(packCatalogApi, "workspace").mockImplementation(() =>
      Promise.resolve(current),
    );
    const toggle = vi
      .spyOn(packCatalogApi, "setWorkspaceEnabled")
      .mockImplementation(() => {
        current = off;
        return Promise.resolve(off);
      });
    const disconnect = vi
      .spyOn(packCatalogApi, "disconnectWorkspace")
      .mockImplementation(() => {
        current = NONE;
        return Promise.resolve();
      });
    mount();
    const state = await screen.findByTestId("ws-catalog-state");
    expect(state).toHaveTextContent("Папка подключена к каталогу.");
    expect(state).toHaveTextContent("Включена");
    expect(state).toHaveTextContent("Применена ревизия dddddddd");

    await userEvent.click(screen.getByTestId("ws-catalog-toggle"));
    expect(toggle).toHaveBeenCalledWith(WS, false);
    expect(await screen.findByText("Выключена")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("ws-catalog-disconnect"));
    expect(
      await screen.findByText(/Версии останутся: существующие проекты/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ws-catalog-disconnect-confirm"));
    expect(disconnect).toHaveBeenCalledWith(WS);
    expect(await screen.findByTestId("ws-catalog-none")).toBeInTheDocument();
  });
});
