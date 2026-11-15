import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { LOCAL_BOOTSTRAP, sessionKeys } from "@entities/session";
import type { PackResponse } from "@shared/api/types";

const PACKS: PackResponse[] = [
  {
    id: "hse-cs-sse",
    name: { ru: "ФКН, ПИ" },
    description: { ru: "Встроенный пак" },
    maintainer: { name: "ФКН", email: "fcs@example.org" },
    templates: [],
    origin: { kind: "builtin" },
  },
  {
    id: "acme-thesis",
    name: { ru: "Выпускные работы Acme" },
    description: { ru: "Подключённый пак" },
    maintainer: { name: "Acme", email: "acme@example.org" },
    templates: [],
    origin: {
      kind: "subscribed",
      source_kind: "git",
      label: "acme-packs",
      url: "https://git.example.org/acme/packs.git",
      ref: "v2026.1.1",
      revision: "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
      replaces_builtin: false,
    },
  },
];

vi.mock("@entities/template-catalog", () => ({
  usePacks: () => ({ data: PACKS, isLoading: false }),
  useVersions: () => ({ data: [], isLoading: false }),
  useVersionDetail: () => ({ data: undefined }),
}));
vi.mock("@entities/hse-person", () => ({ HsePersonLookupButton: () => null }));
vi.mock("@features/folder-picker", () => ({ FolderPickerModal: () => null }));

import { ProjectCreateWizard } from "./ProjectCreateWizard";
import { useCreateWizard } from "../model/useCreateWizard";

describe("мастер проекта: откуда пак", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    useCreateWizard.getState().reset();
  });
  afterEach(() => {
    cleanup();
  });

  it("у подключённого пака строка с источником, у встроенного её нет", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    client.setQueryData(sessionKeys.bootstrap(), LOCAL_BOOTSTRAP);
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ProjectCreateWizard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const lines = screen.getAllByTestId("pack-origin");
    expect(lines).toHaveLength(1);
    const line = lines[0];
    if (!line) throw new Error("нет строки источника");
    expect(within(line).getByText("Подключён: acme-packs")).toBeInTheDocument();
    expect(line).toHaveAttribute(
      "title",
      "https://git.example.org/acme/packs.git @ v2026.1.1",
    );
    expect(
      line.closest("button")?.textContent?.includes("Выпускные работы Acme"),
    ).toBe(true);
  });
});
