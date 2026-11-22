import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { packStudioApi } from "@entities/pack-studio";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { SpaceBar } from "./SpaceBar";
import { renderNav } from "./navTestKit";

describe("SpaceBar: назад, название, «Ещё»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("назад к списку и название пространства", () => {
    renderNav(<SpaceBar />);
    expect(screen.getByTestId("sp-back")).toHaveAttribute(
      "href",
      "/pack-studio",
    );
    expect(screen.getByTestId("sp-back")).toHaveAccessibleName(
      "К списку пространств",
    );
    expect(screen.getByTestId("sp-ws-name")).toHaveTextContent(
      "AlexeyShalaev/hse-doc-studio",
    );
  });

  it("меню: обновить, открыть другое пространство, удалить", async () => {
    const user = userEvent.setup();
    renderNav(<SpaceBar />);
    await user.click(screen.getByTestId("sp-ws-menu"));
    expect(
      await screen.findByRole("menuitem", { name: "Обновить" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", {
        name: "Перейти в пространство «fcs/packs»",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Удалить" }),
    ).toBeInTheDocument();
    // Своё пространство в списке «открыть другое» не повторяется.
    expect(
      screen.queryAllByRole("menuitem", { name: /Перейти в пространство/ }),
    ).toHaveLength(1);
  });

  it("«Обновить» просит обновить пространство", async () => {
    const refresh = vi
      .spyOn(packStudioApi, "refreshWorkspace")
      .mockResolvedValue({} as never);
    const user = userEvent.setup();
    renderNav(<SpaceBar />);
    await user.click(screen.getByTestId("sp-ws-menu"));
    await user.click(await screen.findByTestId("sp-ws-refresh"));
    await waitFor(() => {
      expect(refresh).toHaveBeenCalledWith("gallery-ws");
    });
  });

  it("«Открыть» другое пространство меняет адрес", async () => {
    const user = userEvent.setup();
    renderNav(<SpaceBar />);
    await user.click(screen.getByTestId("sp-ws-menu"));
    await user.click(await screen.findByTestId("sp-ws-switch-gallery-ws-2"));
    // Каркас в тесте не подменяет адрес: переход идёт через роутер провайдера.
    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe(
        "/pack-studio/w/gallery-ws-2",
      );
    });
  });

  it("удаление спрашивает, объясняет и уходит в список", async () => {
    const remove = vi
      .spyOn(packStudioApi, "deleteWorkspace")
      .mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderNav(<SpaceBar />);
    await user.click(screen.getByTestId("sp-ws-menu"));
    await user.click(await screen.findByTestId("sp-ws-delete"));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(
      "Клон в Студии будет удалён, репозиторий на хостинге не меняется.",
    );
    expect(remove).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("sp-ws-delete-confirm"));
    await waitFor(() => {
      expect(remove).toHaveBeenCalledWith("gallery-ws");
      expect(screen.getByTestId("location").textContent).toBe("/pack-studio");
    });
  });

  it("удаление предупреждает о неотправленных правках: они пропадут", async () => {
    const user = userEvent.setup();
    renderNav(<SpaceBar />, {
      changed: [
        "hse-cs-sse/templates/coursework/versions/2026.1.3/version.yaml",
      ],
    });
    await user.click(screen.getByTestId("sp-ws-menu"));
    await user.click(await screen.findByTestId("sp-ws-delete"));
    expect(await screen.findByTestId("sp-ws-delete-unsent")).toHaveTextContent(
      "неотправленные правки: они пропадут вместе с пространством",
    );
  });

  it("правок нет: предупреждения нет", async () => {
    const user = userEvent.setup();
    renderNav(<SpaceBar />, { changed: [] });
    await user.click(screen.getByTestId("sp-ws-menu"));
    await user.click(await screen.findByTestId("sp-ws-delete"));
    await screen.findByRole("dialog");
    expect(screen.queryByTestId("sp-ws-delete-unsent")).toBeNull();
  });
});
