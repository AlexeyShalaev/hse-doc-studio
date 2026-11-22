import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  PackDocLibrarySchema,
  PackVersionModelSchema,
  packStudioApi,
  packStudioKeys,
  type PackVersionModel,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackFormsNamespace } from "@shared/lib/i18n/packFormsNamespace";
import { PackFormPane } from "../PackFormPane";

const REPO = join(
  import.meta.dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
);
const FIXTURES = join(REPO, "contracts", "pack-studio", "fixtures");
const read = (folder: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, folder, name), "utf8"));
const model = (): PackVersionModel =>
  PackVersionModelSchema.parse(read("PackVersionModel", "editable.json"));

const WS = "ws1";
const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.7" };
const DIR = "hse-cs-sse/templates/coursework/versions/2026.1.7";

const renderPane = (
  data: PackVersionModel,
  path: string,
  onOpenFile = vi.fn(),
) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(packStudioKeys.model(WS, REF), data);
  vi.spyOn(packStudioApi, "versionModel").mockResolvedValue(data);
  render(
    <QueryClientProvider client={client}>
      <PackFormPane
        workspaceId={WS}
        path={path}
        onSaved={vi.fn()}
        onOpenFile={onOpenFile}
      />
    </QueryClientProvider>,
  );
  return { onOpenFile };
};

const reportEtag = (data: PackVersionModel) =>
  data.documents[0]?.manifest?.etag ?? null;

describe("формы версии: документы, языки, doc.yaml", () => {
  beforeAll(async () => {
    await loadPackFormsNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("ростер: порядок в version.yaml, группа в doc.yaml документа, переход к форме", async () => {
    const data = model();
    const patch = vi
      .spyOn(packStudioApi, "patchVersionModel")
      .mockResolvedValue(data);
    const { onOpenFile } = renderPane(data, `${DIR}/version.yaml`);

    fireEvent.click(screen.getByTestId("pf-tab-documents"));
    fireEvent.click(
      screen.getByRole("button", { name: "Ниже: Отчёт о курсовом проекте" }),
    );
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    fireEvent.change(screen.getByTestId("pf-doc-group-report"), {
      target: { value: "report" },
    });
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(2);
    });
    fireEvent.click(screen.getByTestId("pf-doc-open-report"));

    expect(patch.mock.calls[0]?.[2]).toEqual({
      file: "version.yaml",
      ops: [{ op: "move", path: ["documents"], index: 0, to: 1 }],
    });
    expect(patch.mock.calls[1]?.[2]).toEqual({
      file: "files/report/doc.yaml",
      ops: [{ op: "set", path: ["group"], value: "report" }],
    });
    expect(patch.mock.calls[1]?.[3]).toBe(reportEtag(data));
    expect(onOpenFile).toHaveBeenCalledWith(`${DIR}/files/report/doc.yaml`);
  });

  it("новый документ из заготовки пространства", async () => {
    const data = model();
    vi.spyOn(packStudioApi, "docLibrary").mockResolvedValue(
      PackDocLibrarySchema.parse(read("PackDocLibrary", "workspace.json")),
    );
    const act = vi
      .spyOn(packStudioApi, "versionModelAction")
      .mockResolvedValue(data);
    renderPane(data, `${DIR}/version.yaml`);

    fireEvent.click(screen.getByTestId("pf-tab-documents"));
    fireEvent.click(screen.getByTestId("pf-doc-add"));
    fireEvent.change(screen.getByTestId("pf-new-id"), {
      target: { value: "review" },
    });
    fireEvent.change(screen.getByTestId("pf-new-label-ru"), {
      target: { value: "Отзыв" },
    });
    const source = await screen.findByTestId("pf-doc-source");
    fireEvent.change(source, {
      target: {
        value: "hse-cs-se/templates/vkr/versions/2026.1.2/files/pdp_review",
      },
    });
    fireEvent.click(screen.getByTestId("pf-new-submit"));

    await vi.waitFor(() => {
      expect(act).toHaveBeenCalledWith(
        WS,
        REF,
        {
          action: "add_document",
          document: "review",
          name: { ru: "Отзыв" },
          source: "hse-cs-se/templates/vkr/versions/2026.1.2/files/pdp_review",
        },
        data.manifest.etag,
      );
    });
  });

  it("удаление документа показывает, где он упомянут", async () => {
    const data = model();
    const act = vi
      .spyOn(packStudioApi, "versionModelAction")
      .mockResolvedValue(data);
    renderPane(data, `${DIR}/version.yaml`);

    fireEvent.click(screen.getByTestId("pf-tab-documents"));
    fireEvent.click(
      screen.getByRole("button", { name: "Удалить: Отчёт о курсовом проекте" }),
    );

    expect(screen.getByTestId("pf-doc-references")).toHaveTextContent(
      "signatures.slots[author].applies_to",
    );
    fireEvent.click(screen.getByTestId("pf-doc-remove-submit"));
    await vi.waitFor(() => {
      expect(act).toHaveBeenCalledWith(
        WS,
        REF,
        { action: "remove_document", document: "report" },
        data.manifest.etag,
      );
    });
  });

  it("языки: файл для всех языков делится по запросу, новый код пишет langs", async () => {
    const data = model();
    const act = vi
      .spyOn(packStudioApi, "versionModelAction")
      .mockResolvedValue(data);
    const patch = vi
      .spyOn(packStudioApi, "patchVersionModel")
      .mockResolvedValue(data);
    renderPane(data, `${DIR}/version.yaml`);

    fireEvent.click(screen.getByTestId("pf-tab-languages"));
    // У отчёта en уже есть у всех редакций: перевод создавать нечего.
    expect(screen.getByTestId("pf-translate-report-en")).toBeDisabled();
    fireEvent.click(screen.getByTestId("pf-split-report/preamble.tex"));
    await vi.waitFor(() => {
      expect(act).toHaveBeenCalledWith(
        WS,
        REF,
        {
          action: "add_translation",
          document: "report",
          lang: "en",
          files: ["report/preamble.tex"],
        },
        data.manifest.etag,
      );
    });
    fireEvent.change(screen.getByTestId("pf-lang-new"), {
      target: { value: "de" },
    });
    fireEvent.click(screen.getByTestId("pf-lang-add"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledWith(
        WS,
        REF,
        {
          file: "version.yaml",
          ops: [{ op: "set", path: ["langs"], value: ["ru", "en", "de"] }],
        },
        data.manifest.etag,
      );
    });
    expect(
      screen.getByRole("button", { name: "Удалить: Английский" }),
    ).toBeDisabled();
  });

  it("форма doc.yaml: проверки из версии, обязательность, новый вариант", async () => {
    const data = model();
    const patch = vi
      .spyOn(packStudioApi, "patchVersionModel")
      .mockResolvedValue(data);
    renderPane(data, `${DIR}/files/report/doc.yaml`);

    expect(screen.getByTestId("pf-doc-form")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("pf-doc-gost"), {
      target: { value: "gost-7.32-2017" },
    });
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(screen.getByTestId("pf-doc-required"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(2);
    });
    fireEvent.click(screen.getByTestId("pf-variant-add"));
    fireEvent.change(screen.getByTestId("pf-new-id"), {
      target: { value: "pptx" },
    });
    fireEvent.change(screen.getByTestId("pf-new-label-ru"), {
      target: { value: "PowerPoint" },
    });
    fireEvent.click(screen.getByTestId("pf-new-submit"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(3);
    });

    expect(patch.mock.calls.map((call) => call[2])).toEqual([
      {
        file: "files/report/doc.yaml",
        ops: [{ op: "set", path: ["gost_ref"], value: "gost-7.32-2017" }],
      },
      {
        file: "files/report/doc.yaml",
        ops: [{ op: "set", path: ["required"], value: false }],
      },
      {
        file: "files/report/doc.yaml",
        ops: [
          {
            op: "set",
            path: ["variants"],
            value: [{ id: "pptx", label: { ru: "PowerPoint" } }],
          },
        ],
      },
    ]);
  });

  it("документ без своей папки: формы нет", () => {
    renderPane(model(), `${DIR}/files/presentation/doc.yaml`);

    expect(screen.queryByTestId("pf-doc-form")).toBeNull();
  });
});
