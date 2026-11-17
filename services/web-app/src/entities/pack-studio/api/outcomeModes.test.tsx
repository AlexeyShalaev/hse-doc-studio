import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { ApiError, apiClient } from "@shared/api";
import {
  COURSEWORK_ATLAS,
  COURSEWORK_COMPARE,
  COURSEWORK_MATRIX,
  installOutcomeReference,
  modesCalls,
  outcomeReference,
  scenarioReference,
  setModesBehavior,
} from "../reference";
import { atlasQuery, packOutcomeApi } from "./outcomeApi";
import {
  classifyOutcomeFailure,
  normalizeAtlasRequest,
  normalizeCompareRequest,
  normalizeImpactRequest,
  normalizeMatrixRequest,
  packOutcomeKeys,
  usePackOutcomeAtlas,
  usePackOutcomeCompare,
  usePackOutcomeImpact,
  usePackOutcomeMatrix,
} from "./outcomeQueries";

// Хуки режимов «Матрица», «Атлас», «Сравнить» и «до и после» на эталонах контракта: запрос уходит в
// транспорт axios, подмена отвечает эталоном со строгим разбором схемами (срез F9).

const WS = "ws-1";
const VKR = { pack: "hse-cs-se", template: "vkr", version: "2026.1.2" };
const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.6" };

const wrapper = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, Wrapper };
};

describe("режимы на эталонах: атлас, матрица, сравнение, до и после", () => {
  beforeAll(() => {
    installOutcomeReference();
  });
  beforeEach(() => {
    outcomeReference.setSource("reference");
    scenarioReference.reset();
    setModesBehavior("normal");
    modesCalls.reset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    setModesBehavior("normal");
    outcomeReference.setBehavior("normal");
  });

  it("атлас курсового разбирается строгой схемой, закрепление режет таблицу", async () => {
    const { Wrapper } = wrapper();
    const free = renderHook(() => usePackOutcomeAtlas(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(free.result.current.isSuccess).toBe(true);
    });
    expect(free.result.current.data?.rows_total).toBe(
      COURSEWORK_ATLAS.rows_total,
    );

    const pinned = renderHook(
      () => usePackOutcomeAtlas(WS, REF, { pin: { supervisor: "company" } }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(pinned.result.current.isSuccess).toBe(true);
    });
    const data = pinned.result.current.data;
    expect(data?.rows.length).toBeLessThan(COURSEWORK_ATLAS.rows.length);
    expect(
      data?.dimensions.find((d) => d.input === "supervisor")?.values,
    ).toEqual(["company"]);
  });

  it("атлас ВКР: 864 строки, ключ разбирается по измерениям", async () => {
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => usePackOutcomeAtlas(WS, VKR, {}), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const atlas = result.current.data;
    expect(atlas?.rows_total).toBe(864);
    expect(atlas?.rows).toHaveLength(864);
    expect(atlas?.rows[0]?.key.split("|")).toHaveLength(
      atlas?.dimensions.length ?? 0,
    );
  });

  it("адрес атласа: pin повторяется, по алфавиту, пустое не пишется", () => {
    expect(atlasQuery({})).toBe("state=work_tree");
    expect(
      atlasQuery({
        state: "head",
        example: "auto:long",
        pin: { staffing: "solo", kind: "research" },
      }),
    ).toBe(
      "state=head&example=auto%3Along&pin=kind%3Aresearch&pin=staffing%3Asolo",
    );
  });

  it("сравнение, матрица и до и после приходят разобранными", async () => {
    const { Wrapper } = wrapper();
    const compare = renderHook(
      () =>
        usePackOutcomeCompare(WS, REF, {
          left: { scenario: "university-supervisor" },
          right: { scenario: "company-supervisor" },
        }),
      { wrapper: Wrapper },
    );
    const matrix = renderHook(() => usePackOutcomeMatrix(WS, REF, {}), {
      wrapper: Wrapper,
    });
    const impact = renderHook(() => usePackOutcomeImpact(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(compare.result.current.isSuccess).toBe(true);
      expect(matrix.result.current.isSuccess).toBe(true);
      expect(impact.result.current.isSuccess).toBe(true);
    });
    expect(compare.result.current.data?.changes.length).toBe(
      COURSEWORK_COMPARE.changes.length,
    );
    expect(matrix.result.current.data?.rows.length).toBe(
      COURSEWORK_MATRIX.rows.length,
    );
    expect(impact.result.current.data?.summary.scenarios_changed).toBe(1);
  });

  it("выключенный запрос не уходит", () => {
    const { Wrapper } = wrapper();
    renderHook(() => usePackOutcomeAtlas(WS, REF, {}, false), {
      wrapper: Wrapper,
    });
    renderHook(() => usePackOutcomeImpact(WS, null, {}), { wrapper: Wrapper });
    expect(modesCalls.count("atlas")).toBe(0);
    expect(modesCalls.count("impact")).toBe(0);
  });

  it("ключи под общим префиксом версии и не зависят от порядка вводных", () => {
    const keys = [
      packOutcomeKeys.atlas(WS, REF, { pin: { a: "1" } }),
      packOutcomeKeys.compare(WS, REF, { left: {}, right: {} }),
      packOutcomeKeys.impact(WS, REF, {}),
      packOutcomeKeys.matrix(WS, REF, {}),
    ];
    const prefix = packOutcomeKeys.version(WS, REF);
    for (const key of keys) {
      expect(key.slice(0, prefix.length)).toEqual([...prefix]);
      expect(key.slice(0, packOutcomeKeys.all(WS).length)).toEqual([
        ...packOutcomeKeys.all(WS),
      ]);
    }
    expect(packOutcomeKeys.atlas(WS, REF, { pin: { b: "2", a: "1" } })).toEqual(
      packOutcomeKeys.atlas(WS, REF, { pin: { a: "1", b: "2" } }),
    );
    expect(
      packOutcomeKeys.compare(WS, REF, {
        left: { inputs: { y: "1", x: "2" } },
        right: {},
      }),
    ).toEqual(
      packOutcomeKeys.compare(WS, REF, {
        left: { inputs: { x: "2", y: "1" }, state: "work_tree" },
        right: { state: "work_tree" },
      }),
    );
  });

  it("запросы приводятся к каноническому виду", () => {
    expect(normalizeAtlasRequest({ pin: {}, scenario: "" })).toEqual({
      state: "work_tree",
    });
    expect(normalizeMatrixRequest({ scenarios: [], against: null })).toEqual({
      state: "work_tree",
    });
    expect(
      normalizeMatrixRequest({ scenarios: ["b", "a"], against: "base" }),
    ).toEqual({
      state: "work_tree",
      scenarios: ["a", "b"],
      against: "base",
    });
    expect(normalizeImpactRequest({})).toEqual({
      base: "base",
      include_atlas: true,
    });
    expect(
      normalizeCompareRequest({
        left: { scenario: null },
        right: { inputs: {} },
      }),
    ).toEqual({ left: { state: "work_tree" }, right: { state: "work_tree" } });
  });

  it("503 outcome_busy повторяется до трёх раз, затем приходит ответ", async () => {
    setModesBehavior("busy");
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => usePackOutcomeAtlas(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(
      () => {
        expect(result.current.isSuccess).toBe(true);
      },
      { timeout: 4000 },
    );
    expect(modesCalls.count("atlas")).toBe(2);
  });

  it("atlas_too_large: пределы из тела, повтор не нужен", async () => {
    setModesBehavior("atlas_too_large");
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => usePackOutcomeAtlas(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(modesCalls.count("atlas")).toBe(1);
    expect(classifyOutcomeFailure(result.current.error)).toEqual({
      kind: "atlas_too_large",
      limit: 2000,
      rows: 6912,
    });
  });

  it("diff_base_unavailable и outcome_too_large опознаются с подробностями", async () => {
    setModesBehavior("no_base");
    const { Wrapper } = wrapper();
    const compare = renderHook(
      () => usePackOutcomeCompare(WS, REF, { left: {}, right: {} }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(compare.result.current.isError).toBe(true);
    });
    expect(classifyOutcomeFailure(compare.result.current.error)).toEqual({
      kind: "diff_base_unavailable",
      reason: "no_base",
    });
    setModesBehavior("too_large");
    const matrix = renderHook(() => usePackOutcomeMatrix(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(matrix.result.current.isError).toBe(true);
    });
    expect(classifyOutcomeFailure(matrix.result.current.error)).toEqual({
      kind: "outcome_too_large",
      limit: 8388608,
      size: 11534336,
    });
  });

  it("разбор прочих отказов", () => {
    const err = (
      status: number,
      code: string,
      data?: Record<string, unknown>,
    ) => new ApiError("x", code, status, data ?? null);
    expect(
      classifyOutcomeFailure(err(503, "outcome_busy", { retry_after_s: 4 })),
    ).toEqual({ kind: "busy", retryAfterS: 4 });
    expect(
      classifyOutcomeFailure(
        err(400, "inputs_invalid", {
          field: "inputs.supervisor",
          value: "firm",
          reason: "value not allowed",
        }),
      ),
    ).toEqual({
      kind: "inputs_invalid",
      field: "inputs.supervisor",
      value: "firm",
      reason: "value not allowed",
    });
    expect(
      classifyOutcomeFailure(
        err(422, "version_unreadable", { reason: "yaml" }),
      ),
    ).toEqual({ kind: "unreadable", reason: "yaml" });
    expect(classifyOutcomeFailure(err(409, "diff_base_unavailable"))).toEqual({
      kind: "diff_base_unavailable",
      reason: null,
    });
    expect(classifyOutcomeFailure(err(0, "network"))).toEqual({
      kind: "offline",
    });
    expect(classifyOutcomeFailure(err(500, "internal_error"))).toEqual({
      kind: "server",
    });
    expect(classifyOutcomeFailure(new Error("x"))).toEqual({ kind: "other" });
  });

  it("повторный запрос идёт с If-None-Match, на 304 возвращается прежний ответ", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({
        status: 200,
        data: COURSEWORK_ATLAS,
        headers: { etag: '"atlas-1"' },
      })
      .mockResolvedValueOnce({ status: 304, data: "", headers: {} });
    const first = await packOutcomeApi.atlas(WS, REF, {});
    expect(first.etag).toBe('"atlas-1"');
    expect(get.mock.calls[0]?.[1]?.headers).toEqual({});
    const second = await packOutcomeApi.atlas(WS, REF, {}, first);
    expect(second).toBe(first);
    expect(get.mock.calls[1]?.[1]?.headers).toEqual({
      "If-None-Match": '"atlas-1"',
    });
    expect(String(get.mock.calls[1]?.[0])).toContain(
      "/outcome/atlas?state=work_tree",
    );
  });

  it("сравнение, матрица и до и после тоже ходят с условным запросом", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValueOnce({
        status: 200,
        data: COURSEWORK_COMPARE,
        headers: { etag: '"c1"' },
      })
      .mockResolvedValueOnce({ status: 304, data: "", headers: {} })
      .mockResolvedValueOnce({
        status: 200,
        data: COURSEWORK_MATRIX,
        headers: { etag: '"m1"' },
      })
      .mockResolvedValueOnce({ status: 304, data: "", headers: {} });
    const body = { left: {}, right: {} };
    const c1 = await packOutcomeApi.compare(WS, REF, body);
    expect(await packOutcomeApi.compare(WS, REF, body, c1)).toBe(c1);
    const m1 = await packOutcomeApi.matrix(WS, REF, {});
    expect(await packOutcomeApi.matrix(WS, REF, {}, m1)).toBe(m1);
    expect(post.mock.calls[1]?.[2]?.headers).toEqual({
      "If-None-Match": '"c1"',
    });
    expect(post.mock.calls[3]?.[2]?.headers).toEqual({
      "If-None-Match": '"m1"',
    });
    expect(String(post.mock.calls[0]?.[0])).toContain("/outcome/compare");
    expect(String(post.mock.calls[2]?.[0])).toContain("/outcome/matrix");
  });

  it("запись сценария сбрасывает матрицу, до и после и сравнения с этим сценарием", async () => {
    const { client, Wrapper } = wrapper();
    const matrix = renderHook(() => usePackOutcomeMatrix(WS, REF, {}), {
      wrapper: Wrapper,
    });
    const withScenario = renderHook(
      () =>
        usePackOutcomeCompare(WS, REF, {
          left: { scenario: "company-supervisor" },
          right: {},
        }),
      { wrapper: Wrapper },
    );
    const without = renderHook(
      () => usePackOutcomeCompare(WS, REF, { left: {}, right: {} }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(matrix.result.current.isSuccess).toBe(true);
      expect(withScenario.result.current.isSuccess).toBe(true);
      expect(without.result.current.isSuccess).toBe(true);
    });
    const { useWritePackScenario } = await import("./outcomeQueries");
    const writer = renderHook(
      () => useWritePackScenario(WS, REF.pack, REF.template),
      { wrapper: Wrapper },
    );
    const entry = scenarioReference.entries()[0];
    const before = modesCalls.count("matrix") + modesCalls.count("compare");
    await writer.result.current.mutateAsync({
      scenario: "company-supervisor",
      body: {
        scenario: entry?.scenario ?? { format: 1, name: { ru: "x" } },
      } as never,
      ifMatch: entry?.etag ?? null,
    });
    await waitFor(() => {
      // Матрица и сравнение с этим сценарием перечитаны, сравнение без сценария нет.
      expect(modesCalls.count("matrix") + modesCalls.count("compare")).toBe(
        before + 2,
      );
    });
    expect(
      client.getQueryState(
        packOutcomeKeys.compare(WS, REF, { left: {}, right: {} }),
      )?.isInvalidated,
    ).toBe(false);
  });
});
