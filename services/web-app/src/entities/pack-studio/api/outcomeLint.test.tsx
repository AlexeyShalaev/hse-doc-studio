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
  COURSEWORK_LINT,
  VKR_LINT,
  installOutcomeReference,
  modesCalls,
  outcomeReference,
  referenceLint,
  scenarioReference,
  setModesBehavior,
} from "../reference";
import { lintQuery, packOutcomeApi } from "./outcomeApi";
import { PackOutcomeLintSchema } from "./outcome";
import {
  classifyOutcomeFailure,
  isRateLimited,
  normalizeLintRequest,
  packOutcomeKeys,
  rateLimitSeconds,
  usePackOutcomeLint,
  useWritePackScenario,
} from "./outcomeQueries";

// Линтер результата (срез F11): клиент, ключи, ETag, повторы и разбор отказов на эталонах контракта.

const WS = "ws-1";
const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.6" };
const VKR = { pack: "hse-cs-se", template: "vkr", version: "2026.1.2" };

const wrapper = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, Wrapper };
};

describe("линтер результата: клиент и хуки (F11)", () => {
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

  it("эталоны контракта проходят строгую схему, у ВКР предупреждения без ошибок", () => {
    expect(PackOutcomeLintSchema.parse(VKR_LINT).warnings).toBe(12);
    expect(VKR_LINT.errors).toBe(0);
    const levels = new Set(COURSEWORK_LINT.findings.map((f) => f.severity));
    expect([...levels].sort()).toEqual(["error", "info", "warning"]);
    expect(COURSEWORK_LINT.findings.every((f) => f.witnesses.length <= 3)).toBe(
      true,
    );
  });

  it("адрес: jinja пишется только когда нужен, запрос приводится к каноническому виду", () => {
    expect(lintQuery({})).toBe("state=work_tree");
    expect(lintQuery({ state: "head", jinja: true })).toBe(
      "state=head&jinja=true",
    );
    expect(normalizeLintRequest({})).toEqual({ state: "work_tree" });
    expect(normalizeLintRequest({ jinja: true })).toEqual({
      state: "work_tree",
      jinja: true,
    });
    // Jinja читает только рабочее дерево: на других состояниях ключ тот же, что без Jinja.
    expect(normalizeLintRequest({ state: "base", jinja: true })).toEqual({
      state: "base",
    });
  });

  it("ключ под общим префиксом версии: сброс packOutcomeKeys.all его затрагивает", () => {
    const key = packOutcomeKeys.lint(WS, REF, { jinja: true });
    expect(key.slice(0, 3)).toEqual(packOutcomeKeys.all(WS).slice(0, 3));
    expect(key.slice(0, packOutcomeKeys.all(WS).length)).toEqual(
      packOutcomeKeys.all(WS),
    );
    expect(key[7]).toBe("lint");
    expect(packOutcomeKeys.lint(WS, REF, {})).not.toEqual(key);
  });

  it("хук отдаёт находки и покрытие, выключенный запрос не уходит, но читает кэш", async () => {
    const { client, Wrapper } = wrapper();
    const idle = renderHook(() => usePackOutcomeLint(WS, REF, {}, false), {
      wrapper: Wrapper,
    });
    expect(idle.result.current.fetchStatus).toBe("idle");
    expect(modesCalls.count("lint")).toBe(0);
    const live = renderHook(() => usePackOutcomeLint(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(live.result.current.isSuccess).toBe(true);
    });
    expect(live.result.current.data?.findings).toHaveLength(4);
    expect(live.result.current.data?.coverage.percent).toBe(78.1);
    expect(modesCalls.count("lint")).toBe(1);
    // Тот же ключ в выключенном хуке виден из кэша: значок в панели берёт числа отсюда.
    await waitFor(() => {
      expect(idle.result.current.data?.errors).toBe(1);
    });
    expect(
      client.getQueryData(packOutcomeKeys.lint(WS, REF, {})),
    ).toBeDefined();
  });

  it("ВКР приходит своим эталоном, Jinja и состояние отражаются в ответе", async () => {
    const { Wrapper } = wrapper();
    const vkr = renderHook(() => usePackOutcomeLint(WS, VKR, { jinja: true }), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(vkr.result.current.isSuccess).toBe(true);
    });
    expect(vkr.result.current.data?.warnings).toBe(12);
    expect(vkr.result.current.data?.jinja).toBe("ran");
    const base = renderHook(
      () => usePackOutcomeLint(WS, VKR, { state: "base", jinja: true }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(base.result.current.isSuccess).toBe(true);
    });
    expect(base.result.current.data?.jinja).toBe("unavailable");
  });

  it("повторный запрос идёт с If-None-Match, на 304 возвращается прежний ответ", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({
        status: 200,
        data: COURSEWORK_LINT,
        headers: { etag: '"lint-1"' },
      })
      .mockResolvedValueOnce({ status: 304, data: "", headers: {} });
    const first = await packOutcomeApi.lint(WS, REF, {});
    expect(first.etag).toBe('"lint-1"');
    const second = await packOutcomeApi.lint(WS, REF, { jinja: true }, first);
    expect(second).toBe(first);
    expect(get.mock.calls[1]?.[1]?.headers).toEqual({
      "If-None-Match": '"lint-1"',
    });
    expect(String(get.mock.calls[1]?.[0])).toContain(
      "/outcome/lint?state=work_tree&jinja=true",
    );
  });

  it("503 outcome_busy повторяется сам, затем приходит ответ", async () => {
    setModesBehavior("busy");
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => usePackOutcomeLint(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(
      () => {
        expect(result.current.isSuccess).toBe(true);
      },
      { timeout: 4000 },
    );
    expect(modesCalls.count("lint")).toBe(2);
  });

  it("429 rate_limited повторяется сам через retry_after, затем приходит ответ", async () => {
    setModesBehavior("lint_rate_limited");
    const { Wrapper } = wrapper();
    const { result } = renderHook(
      () => usePackOutcomeLint(WS, REF, { jinja: true }),
      { wrapper: Wrapper },
    );
    await waitFor(
      () => {
        expect(result.current.failureCount).toBe(1);
      },
      { timeout: 2000 },
    );
    expect(classifyOutcomeFailure(result.current.failureReason)).toEqual({
      kind: "rate_limited",
      retryAfterS: 1,
    });
    await waitFor(
      () => {
        expect(result.current.isSuccess).toBe(true);
      },
      { timeout: 4000 },
    );
    expect(modesCalls.count("lint")).toBe(2);
  });

  it("отказы опознаются: лимит частоты, версия не читается, нет базы", () => {
    const limited = new ApiError("slow", "rate_limited", 429, {
      retry_after: 12,
    });
    expect(isRateLimited(limited)).toBe(true);
    expect(rateLimitSeconds(limited)).toBe(12);
    // Без заголовка Retry-After ждём десять секунд, больше тридцати не ждём.
    expect(rateLimitSeconds(new ApiError("slow", "rate_limited", 429))).toBe(
      10,
    );
    expect(
      rateLimitSeconds(
        new ApiError("slow", "rate_limited", 429, { retry_after: 900 }),
      ),
    ).toBe(30);
    expect(
      classifyOutcomeFailure(
        new ApiError("x", "version_unreadable", 422, { reason: "bad yaml" }),
      ),
    ).toEqual({ kind: "unreadable", reason: "bad yaml" });
    expect(
      classifyOutcomeFailure(
        new ApiError("x", "diff_base_unavailable", 409, { reason: "no_base" }),
      ),
    ).toEqual({ kind: "diff_base_unavailable", reason: "no_base" });
  });

  it("запись сценария сбрасывает линтер: покрытие считается по сценариям", async () => {
    const { client, Wrapper } = wrapper();
    const lint = renderHook(() => usePackOutcomeLint(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(lint.result.current.isSuccess).toBe(true);
    });
    const writer = renderHook(
      () => useWritePackScenario(WS, REF.pack, REF.template),
      { wrapper: Wrapper },
    );
    const entry = scenarioReference.entries()[0];
    await writer.result.current.mutateAsync({
      scenario: "company-supervisor",
      body: {
        scenario: entry?.scenario ?? { format: 1, name: { ru: "x" } },
      } as never,
      ifMatch: entry?.etag ?? null,
    });
    await waitFor(() => {
      expect(modesCalls.count("lint")).toBe(2);
    });
    expect(
      client.getQueryState(packOutcomeKeys.lint(WS, REF, {}))?.isInvalidated,
    ).toBe(false);
  });

  it("варианты подмены: пустой, атлас пропущен", () => {
    const empty = referenceLint("lint_empty");
    expect(empty.findings).toEqual([]);
    expect(empty.coverage.percent).toBe(100);
    const skipped = referenceLint("lint_atlas_skipped");
    expect(skipped.atlas_skipped).toBe(true);
    expect(skipped.coverage.approximate).toBe(true);
    expect(skipped.findings.some((f) => f.rule_id === "atlas-skipped")).toBe(
      true,
    );
  });
});
