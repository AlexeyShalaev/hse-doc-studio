import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { PackStudioAdminSchema, packStudioApi } from "@entities/pack-studio";
import { i18n, loadAdminNamespaces } from "@shared/lib";
import { PackStudioAdminPage } from "./PackStudioAdminPage";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures/PackStudioAdmin",
);
const admin = (name: string) =>
  PackStudioAdminSchema.parse(
    JSON.parse(readFileSync(join(FIXTURES, `${name}.json`), "utf8")),
  );

const mount = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <PackStudioAdminPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("админка: Студия шаблонов", () => {
  beforeAll(async () => {
    await loadAdminNamespaces(["packStudio"]);
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("включение раздела и права людям и группам, снятие права", async () => {
    const data = admin("enabled");
    vi.spyOn(packStudioApi, "admin").mockResolvedValue(data);
    const setAdmin = vi
      .spyOn(packStudioApi, "setAdmin")
      .mockResolvedValue({ ...data, enabled: false });
    const remove = vi.spyOn(packStudioApi, "removeGrant").mockResolvedValue();
    mount();
    const toggle = await screen.findByTestId("ps-admin-enabled");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Анна Петрова")).toBeInTheDocument();
    expect(screen.getByText(/группа · ФКН/)).toBeInTheDocument();

    await userEvent.click(toggle);
    await waitFor(() => {
      expect(setAdmin).toHaveBeenCalledWith(false);
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Снять право у «Анна Петрова»" }),
    );
    expect(remove).toHaveBeenCalledWith(data.grants[0]?.id);
  });

  it("включение из окружения: переключатель закрыт, прав нет", async () => {
    vi.spyOn(packStudioApi, "admin").mockResolvedValue(admin("locked_off"));
    mount();
    expect(await screen.findByTestId("ps-admin-enabled")).toBeDisabled();
    expect(screen.getByText("Право пока никому не выдано")).toBeInTheDocument();
  });
});
