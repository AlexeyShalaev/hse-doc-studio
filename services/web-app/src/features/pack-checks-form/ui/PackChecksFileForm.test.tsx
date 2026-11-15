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
  PackChecksSchema,
  PackPreviewBuildSchema,
  PackPreviewOptionsSchema,
  packChecksApi,
  packStudioApi,
} from "@entities/pack-studio";
import { resetPreviewSelections } from "@features/pack-preview";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { PackChecksConfigForm } from "./PackChecksConfigForm";
import { PackChecksFileForm } from "./PackChecksFileForm";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );

const DATA = fixture(PackChecksSchema, "PackChecks", "version");
const OPTIONS = fixture(
  PackPreviewOptionsSchema,
  "PackPreviewOptions",
  "coursework",
);
const BUILD = fixture(
  PackPreviewBuildSchema,
  "PackPreviewBuild",
  "with_checks",
);
const WS = DATA.workspace_id;
const FILE = DATA.files[0]!;

const wrap = (node: React.ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
};

describe("формы проверок", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    resetPreviewSelections();
  });

  it("параметр структурной проверки сохраняется правкой правила с If-Match", async () => {
    vi.spyOn(packChecksApi, "get").mockResolvedValue(DATA);
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
    const patch = vi.spyOn(packChecksApi, "patchFile").mockResolvedValue(DATA);
    const onSaved = vi.fn();
    wrap(
      <PackChecksFileForm
        workspaceId={WS}
        path={FILE.path}
        onSaved={onSaved}
      />,
    );

    const left = await screen.findByTestId("rule-0-param-expected.left_mm");
    fireEvent.change(left, { target: { value: "25" } });
    fireEvent.click(screen.getByTestId("rule-0-save"));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    const [, , name, body, etag] = patch.mock.calls[0]!;
    expect(name).toBe(FILE.name);
    expect(etag).toBe(FILE.etag);
    expect(body.ops[0]).toMatchObject({
      op: "set_rule",
      index: 0,
      rule: {
        params: {
          check: "page_geometry",
          expected: { left_mm: 25, right_mm: 15, top_mm: 20, bottom_mm: 20 },
          tolerance_mm: 1,
        },
      },
    });
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(FILE.path);
    });
  });

  it("«Проверить на предпросмотре»: сборка с проверками, находки у правила", async () => {
    vi.spyOn(packChecksApi, "get").mockResolvedValue(DATA);
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
    const done = {
      ...BUILD,
      checks: [
        {
          rule_id: "gost-7.32-2017/page-margins",
          severity: "warn",
          message: "Левое поле 25 мм",
          file: "report/report.tex",
          line: null,
        },
      ],
    };
    const start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([done]);
    vi.spyOn(packStudioApi, "previewBuild").mockResolvedValue(done);
    wrap(
      <PackChecksFileForm
        workspaceId={WS}
        path={FILE.path}
        onSaved={vi.fn()}
      />,
    );

    fireEvent.click(await screen.findByTestId("checks-run-start"));

    await waitFor(() => {
      expect(start).toHaveBeenCalled();
    });
    expect(start.mock.calls[0]?.[2]).toMatchObject({ checks: true });
    expect(await screen.findByTestId("checks-run-done")).toHaveTextContent(
      "1 находка",
    );
    expect(screen.getByTestId("rule-0-result")).toHaveTextContent("1 находка");
    expect(screen.getByTestId("rule-1-result")).toHaveTextContent(
      "Без находок",
    );
  });

  it("checks_version: правило выключается записью всего блока", async () => {
    vi.spyOn(packChecksApi, "get").mockResolvedValue(DATA);
    const put = vi.spyOn(packChecksApi, "putConfig").mockResolvedValue(DATA);
    wrap(
      <PackChecksConfigForm
        workspaceId={WS}
        path={DATA.config.path}
        onSaved={vi.fn()}
      />,
    );

    fireEvent.click(await screen.findByTestId("disable-gost-7.32-2017/intro"));

    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    expect(put.mock.calls[0]?.[2]).toEqual({
      disabled_categories: ["typography"],
      disabled: ["gost-7.32-2017/font-size", "gost-7.32-2017/intro"],
      severity_override: { "gost-7.32-2017/page-margins": "err" },
    });
    expect(put.mock.calls[0]?.[3]).toBe(DATA.config.etag);
  });
});
