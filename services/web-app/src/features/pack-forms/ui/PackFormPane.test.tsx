import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ComponentProps } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  PackVersionModelSchema,
  packStudioApi,
  packStudioKeys,
  type PackVersionModel,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackFormsNamespace } from "@shared/lib/i18n/packFormsNamespace";
import { PackFormPane } from "./PackFormPane";

const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const fixture = (name: string): PackVersionModel =>
  PackVersionModelSchema.parse(
    JSON.parse(
      readFileSync(
        join(
          REPO,
          "contracts",
          "pack-studio",
          "fixtures",
          "PackVersionModel",
          name,
        ),
        "utf8",
      ),
    ),
  );

const WS = "ws1";
const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.7" };
const PATH = "hse-cs-sse/templates/coursework/versions/2026.1.7/version.yaml";

const renderPane = (
  data: PackVersionModel,
  extra: Partial<ComponentProps<typeof PackFormPane>> = {},
) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(packStudioKeys.model(WS, REF), data);
  vi.spyOn(packStudioApi, "versionModel").mockResolvedValue(data);
  const onSaved = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <PackFormPane workspaceId={WS} path={PATH} onSaved={onSaved} {...extra} />
    </QueryClientProvider>,
  );
  return { client, onSaved };
};

const commit = (testId: string, value: string) => {
  const input = screen.getByTestId(testId);
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value } });
  fireEvent.blur(input);
};

describe("формы версии: поля и анкеты", () => {
  beforeAll(async () => {
    await loadPackFormsNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("поле: образец, где печатается и правка подписи точечной правкой", async () => {
    const data = fixture("editable.json");
    const patch = vi
      .spyOn(packStudioApi, "patchVersionModel")
      .mockResolvedValue({ ...data, changed: [PATH] });
    const { onSaved } = renderPane(data);

    expect(screen.getByTestId("pf-group-study")).toHaveTextContent("1 поле");
    fireEvent.click(screen.getByTestId("pf-field-year"));
    expect(screen.getByTestId("field-usage")).toHaveTextContent("\\hseYear");
    expect(screen.getByTestId("field-usage")).toHaveTextContent(
      "Отчёт о курсовом проекте",
    );
    // `auto: academic_year` подставлен в образец так же, как в мастере проекта.
    expect(
      screen.getByTestId("field-sample").querySelector("input"),
    ).not.toHaveValue("");

    commit("pf-field-label-ru", "Год защиты");

    await vi.waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith([PATH]);
    });
    expect(patch).toHaveBeenCalledWith(
      WS,
      REF,
      {
        file: "version.yaml",
        ops: [
          {
            op: "set",
            path: ["meta_fields", "year", "label"],
            value: { ru: "Год защиты", en: "Academic year" },
          },
        ],
      },
      data.manifest.etag,
    );
  });

  it("пустой необязательный ключ уходит из YAML, а порядок групп меняется перемещением", async () => {
    const data = fixture("editable.json");
    const patch = vi
      .spyOn(packStudioApi, "patchVersionModel")
      .mockResolvedValue(data);
    renderPane(data);

    fireEvent.click(screen.getByTestId("pf-field-year"));
    commit("pf-field-placeholder", "");
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(screen.getByRole("button", { name: "Ниже: Учёба" }));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(2);
    });

    expect(patch.mock.calls.map((call) => call[2].ops)).toEqual([
      [{ op: "delete", path: ["meta_fields", "year", "placeholder"] }],
      [{ op: "move", path: ["meta_groups"], index: 0, to: 1 }],
    ]);
  });

  it("поле, которое нигде не печатается, помечено", () => {
    const data = fixture("editable.json");
    renderPane({ ...data, usage: [] });

    fireEvent.click(screen.getByTestId("pf-field-proposal_stage"));

    expect(screen.getByTestId("field-unused")).toBeInTheDocument();
  });

  it("переименование ключа идёт операцией на всю версию", async () => {
    const data = fixture("editable.json");
    const act = vi
      .spyOn(packStudioApi, "versionModelAction")
      .mockResolvedValue(data);
    renderPane(data);

    fireEvent.click(screen.getByTestId("pf-field-year"));
    fireEvent.click(screen.getByTestId("pf-field-rename"));
    fireEvent.change(screen.getByTestId("pf-rename-to"), {
      target: { value: "proposal_stage" },
    });
    expect(screen.getByTestId("pf-rename-submit")).toBeDisabled();
    fireEvent.change(screen.getByTestId("pf-rename-to"), {
      target: { value: "defence_year" },
    });
    fireEvent.click(screen.getByTestId("pf-rename-submit"));

    await vi.waitFor(() => {
      expect(act).toHaveBeenCalledWith(
        WS,
        REF,
        { action: "rename_field", field: "year", to: "defence_year" },
        data.manifest.etag,
      );
    });
  });

  it("новое поле и отказ сервера с причиной", async () => {
    const data = fixture("editable.json");
    vi.spyOn(packStudioApi, "patchVersionModel").mockRejectedValue(
      new ApiError("x", "model_invalid", 400, {
        reason: "/meta_fields/city/type: 'x' is not one of",
      }),
    );
    renderPane(data);

    fireEvent.click(screen.getByTestId("pf-field-add"));
    fireEvent.change(screen.getByTestId("pf-new-id"), {
      target: { value: "city" },
    });
    fireEvent.change(screen.getByTestId("pf-new-label-ru"), {
      target: { value: "Город" },
    });
    fireEvent.click(screen.getByTestId("pf-new-submit"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "/meta_fields/city/type",
    );
    expect(packStudioApi.patchVersionModel).toHaveBeenCalledWith(
      WS,
      REF,
      {
        file: "version.yaml",
        ops: [
          {
            op: "set",
            path: ["meta_fields", "city"],
            value: {
              type: "string",
              label: { ru: "Город" },
              required_at: "never",
            },
          },
        ],
      },
      data.manifest.etag,
    );
  });

  it("анкета: образец поля движком анкет и правка варианта", async () => {
    const data = fixture("editable.json");
    const patch = vi
      .spyOn(packStudioApi, "patchVersionModel")
      .mockResolvedValue(data);
    renderPane(data);

    fireEvent.click(screen.getByTestId("pf-tab-forms"));
    fireEvent.click(screen.getByTestId("pf-form-ai_declaration"));
    fireEvent.click(screen.getByTestId("pf-form-field-used_ai"));

    expect(screen.getByTestId("form-field-sample")).toHaveTextContent(
      "Использование ИИ",
    );
    fireEvent.click(screen.getByTestId("pf-form-required-for-pack"));

    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledWith(
        WS,
        REF,
        {
          file: "version.yaml",
          ops: [{ op: "delete", path: ["forms", 0, "required_for_pack"] }],
        },
        data.manifest.etag,
      );
    });
  });

  it("выпущенная версия только для чтения", () => {
    renderPane({ ...fixture("editable.json"), read_only: "version_released" });

    expect(screen.queryByTestId("pf-field-add")).toBeNull();
    fireEvent.click(screen.getByTestId("pf-field-year"));
    expect(screen.getByTestId("pf-field-label-ru")).toBeDisabled();
  });

  it("раздел задан снаружи: одна форма без полосы вкладок и без плашки о выпущенной версии", () => {
    renderPane(
      { ...fixture("editable.json"), read_only: "version_released" },
      { section: "forms" },
    );

    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryByTestId("pf-field-year")).toBeNull();
    expect(screen.queryByText(/Версия выпущена/)).toBeNull();
    expect(screen.queryByTestId("pf-field-add")).toBeNull();
  });

  it("раздел «Поля» без вкладок показывает поля", () => {
    renderPane(fixture("editable.json"), { section: "fields" });

    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.getByTestId("pf-field-year")).toBeInTheDocument();
  });
});
