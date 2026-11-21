import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ZodType } from "zod";
import {
  PackLintSchema,
  PackPreviewOptionsSchema,
  PackSubmissionRoutesSchema,
  PackSubmissionSchema,
  packStudioApi,
  packSubmissionApi,
  type PackSubmission,
} from "@entities/pack-studio";
import { resetPreviewSelections } from "@features/pack-preview";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { PackSubmissionForm } from "./PackSubmissionForm";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );

const DATA = fixture(PackSubmissionSchema, "PackSubmission", "profiles");
const ROUTES = fixture(
  PackSubmissionRoutesSchema,
  "PackSubmissionRoutes",
  "company_supervisor",
);
const OPTIONS = fixture(
  PackPreviewOptionsSchema,
  "PackPreviewOptions",
  "coursework",
);
const LINT = fixture(PackLintSchema, "PackLint", "version");
const WS = DATA.workspace_id;
const PATH = DATA.path;

const mount = (data: PackSubmission = DATA) => {
  vi.spyOn(packSubmissionApi, "get").mockResolvedValue(data);
  vi.spyOn(packSubmissionApi, "routes").mockResolvedValue(ROUTES);
  vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
  vi.spyOn(packStudioApi, "lint").mockResolvedValue(LINT);
  const patch = vi.spyOn(packSubmissionApi, "patch").mockResolvedValue(data);
  const onSaved = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <PackSubmissionForm
        workspaceId={WS}
        path={PATH}
        revision={DATA.etag}
        onSaved={onSaved}
      />
    </QueryClientProvider>,
  );
  return { patch, onSaved };
};

describe("форма точек сдачи", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    resetPreviewSelections();
  });

  it("способ подписи пункта пишется правкой записи с If-Match", async () => {
    const { patch, onSaved } = mount();
    const box = await screen.findByTestId("p0-item-0-method-author-detached");
    expect(box).toBeChecked();

    fireEvent.click(box);

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    expect(patch).toHaveBeenCalledWith(
      WS,
      { pack: "hse-cs-sse", template: "coursework", version: "2026.1.7" },
      {
        ops: [
          {
            op: "set_entry",
            profile: 0,
            entries: "items",
            index: 0,
            item: {
              doc_id: "topic_application",
              signatures: ["author", "supervisor"],
              methods: { author: ["image"], supervisor: ["image", "detached"] },
              skip_if_nda: false,
              supported_kinds: [],
            },
          },
        ],
      },
      DATA.etag,
    );
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(PATH);
    });
  });

  it("битая запись пресета видна с причиной, маршрут в этой комбинации посчитан", async () => {
    mount();

    expect(
      (
        await screen.findAllByText(
          /doc_id and slot_id must be non-empty strings/,
        )
      ).length,
    ).toBeGreaterThan(0);
    const preview = await screen.findByTestId("route-preview-topic-approval");
    expect(preview).toHaveTextContent("Академический руководитель");
    expect(preview).toHaveTextContent(
      "если научный руководитель указан и из компании",
    );
    expect(screen.getAllByTestId("route-preview-skipped")[0]).toHaveTextContent(
      "Не при этих условиях",
    );
  });

  it("свой порядок точки снимается: ключ уходит, действует порядок версии", async () => {
    const { patch } = mount();

    fireEvent.click(await screen.findByTestId("profile-0-route-inherit"));

    await waitFor(() => {
      expect(patch).toHaveBeenCalled();
    });
    expect(patch.mock.calls[0]?.[2]).toEqual({
      ops: [{ op: "set_profile_route", profile: 0, steps: null }],
    });
  });

  it("подсказка срока с датой не сохраняется", async () => {
    const { patch } = mount();
    const ru = await screen.findByTestId("head-0-hint-ru");

    fireEvent.change(ru, { target: { value: "До 15 ноября" } });

    expect(screen.getByText(/Похоже на конкретную дату/)).toBeInTheDocument();
    expect(screen.getByTestId("head-0-save")).toBeDisabled();
    expect(patch).not.toHaveBeenCalled();
  });

  it("выпущенная версия только для просмотра", async () => {
    mount({ ...DATA, read_only: "version_released" });

    expect(
      await screen.findByTestId("p0-item-0-method-author-detached"),
    ).toBeDisabled();
    expect(screen.queryByTestId("profile-new")).not.toBeInTheDocument();
  });

  it("отказ сервера показан с причиной", async () => {
    const { patch } = mount();
    patch.mockRejectedValueOnce(
      new ApiError("Правку нельзя записать", "submission_invalid", 400, {
        reason: "profile final: deadline_hint.ru names a concrete date",
      }),
    );

    fireEvent.click(await screen.findByTestId("p0-item-0-method-author-image"));

    expect(await screen.findByTestId("submission-error")).toHaveTextContent(
      "names a concrete date",
    );
  });
});
