import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ZodType } from "zod";
import {
  PackScaffoldCreatedSchema,
  PackScaffoldOptionsSchema,
  PackStudioErrorBodySchema,
  packStudioApi,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { NewPackDialog, type NewPackTarget } from "./NewPackDialog";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );

const OPTIONS = fixture(
  PackScaffoldOptionsSchema,
  "PackScaffoldOptions",
  "folder",
);
const CREATED = fixture(
  PackScaffoldCreatedSchema,
  "PackScaffoldCreated",
  "minimal",
);

const mount = (target: NewPackTarget) => {
  vi.spyOn(packStudioApi, "scaffoldOptions").mockResolvedValue(OPTIONS);
  const props = { onClose: vi.fn(), onCreated: vi.fn() };
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <NewPackDialog workspaceId="ws-1" target={target} {...props} />
    </QueryClientProvider>,
  );
  return props;
};

describe("«Новый пак» и «Новый шаблон»", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("новый пак из минимальной заготовки: умолчания из профиля, занятый id подсвечен", async () => {
    const create = vi
      .spyOn(packStudioApi, "createPack")
      .mockResolvedValue(CREATED);
    const props = mount({ kind: "pack" });

    const packId = await screen.findByTestId("scaffold-pack-id");
    await userEvent.type(packId, "hse-cs-sse");
    expect(
      screen.getByText(
        "Такое короткое имя уже занято в пространстве или в каталоге Студии.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("scaffold-submit")).toBeDisabled();

    await userEvent.clear(packId);
    await userEvent.type(packId, "spbu-math");
    await userEvent.type(screen.getByTestId("scaffold-pack-name-ru"), "СПбГУ");
    await userEvent.type(screen.getByTestId("scaffold-template-id"), "kr");
    await userEvent.type(
      screen.getByTestId("scaffold-template-name-ru"),
      "Курсовая",
    );
    await userEvent.click(screen.getByTestId("scaffold-submit"));

    await waitFor(() => {
      expect(props.onCreated).toHaveBeenCalledWith(CREATED);
    });
    expect(create).toHaveBeenCalledWith("ws-1", {
      id: "spbu-math",
      name: { ru: "СПбГУ", en: "" },
      maintainer: { name: "Ирина Смирнова", email: "author@example.org" },
      license: "Apache-2.0",
      source: null,
      template: { id: "kr", name: { ru: "Курсовая", en: "" } },
      scaffold: { kind: "minimal" },
      version: "2026.1",
    });
  });

  it("достаточно названий: короткие имена строятся сами, остальное под «Дополнительно»", async () => {
    const create = vi
      .spyOn(packStudioApi, "createPack")
      .mockResolvedValue(CREATED);
    mount({ kind: "pack" });

    await userEvent.type(
      await screen.findByTestId("scaffold-pack-name-ru"),
      "Системная инженерия",
    );
    await userEvent.type(
      screen.getByTestId("scaffold-template-name-ru"),
      "Курсовая работа",
    );
    // Первым стоит то, без чего не обойтись; остальное свёрнуто.
    const more = screen.getByTestId("scaffold-more");
    expect(more.tagName).toBe("DETAILS");
    expect(more).not.toHaveAttribute("open");
    expect(more).toHaveTextContent("Дополнительно");
    expect(screen.getByTestId("scaffold-pack-id")).toHaveValue(
      "sistemnaya-inzheneriya",
    );
    expect(screen.getByTestId("scaffold-template-id")).toHaveValue(
      "kursovaya_rabota",
    );
    await userEvent.click(screen.getByTestId("scaffold-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalled();
    });
    expect(create.mock.calls[0]?.[1]).toMatchObject({
      id: "sistemnaya-inzheneriya",
      template: { id: "kursovaya_rabota" },
    });
  });

  it("в окне нет жаргона первого экрана: «Id», «SPDX», «манифест», «beta»", async () => {
    mount({ kind: "pack" });
    const dialog = await screen.findByRole("dialog");
    const text = dialog.textContent ?? "";
    for (const word of ["Id ", "SPDX", "манифест", "beta", "реестр выпусков"]) {
      expect(text).not.toContain(word);
    }
  });

  it("новый шаблон копией: версия по умолчанию первого источника, отказ сервера виден", async () => {
    const body = fixture(
      PackStudioErrorBodySchema,
      "PackStudioErrorBody",
      "id_invalid",
    );
    const { detail, code, ...data } = body;
    const create = vi
      .spyOn(packStudioApi, "createTemplate")
      .mockRejectedValue(new ApiError(detail, code, 400, data));
    mount({ kind: "template", pack: "spbu-cs" });

    await userEvent.type(
      await screen.findByTestId("scaffold-template-id"),
      "vkr",
    );
    await userEvent.type(
      screen.getByTestId("scaffold-template-name-en"),
      "Thesis",
    );
    await userEvent.click(screen.getByTestId("scaffold-kind-copy"));
    await userEvent.click(screen.getByTestId("scaffold-submit"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Недопустимый id",
    );
    expect(create).toHaveBeenCalledWith("ws-1", "spbu-cs", {
      id: "vkr",
      name: { ru: "", en: "Thesis" },
      scaffold: {
        kind: "copy",
        source: {
          origin: "workspace",
          pack: "spbu-cs",
          template: "coursework",
          version: "2026.1",
        },
      },
      version: "2026.1",
    });
  });
});
