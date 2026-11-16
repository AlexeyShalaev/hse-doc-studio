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
  installOutcomeReference,
  outcomeReference,
  scenarioReference,
  setExplainBehavior,
} from "../reference";
import { packOutcomeApi } from "./outcomeApi";
import {
  busyDelaySeconds,
  isElementGone,
  isOutcomeBusy,
  normalizeOutcomeRequest,
  packOutcomeKeys,
  retryOutcome,
  useDeletePackScenario,
  usePackOutcome,
  usePackOutcomeExplain,
  usePackOutcomeInputs,
  usePackScenarioRun,
  usePackScenarios,
  useWritePackScenario,
} from "./outcomeQueries";
import { PackStaleFileError } from "./packStudioApi";

// Хуки результата на эталонах контракта: запрос уходит в транспорт axios, подмена отвечает
// эталоном со строгим разбором схемами. Тот же код, который позже получит настоящий сервер.

const REF = { pack: "hse-cs-se", template: "vkr", version: "2026.1.2" };
const WS = "ws-1";
const REF2 = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
};

const wrapper = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, Wrapper };
};

describe("хуки результата на эталонах", () => {
  beforeAll(() => {
    installOutcomeReference();
  });
  // По умолчанию запросы идут настоящему серверу; тесты работают на эталонах.
  beforeEach(() => {
    outcomeReference.setSource("reference");
    scenarioReference.reset();
  });
  afterEach(() => {
    outcomeReference.setSource("reference");
    outcomeReference.setBehavior("normal");
    scenarioReference.reset();
  });

  it("результат несёт адрес запроса и вводные поверх эталона", async () => {
    const { Wrapper } = wrapper();
    const { result } = renderHook(
      () =>
        usePackOutcome(WS, REF, {
          state: "head",
          inputs: { staffing: "team2" },
        }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const data = result.current.data;
    expect(data?.workspace_id).toBe(WS);
    expect(data?.template).toBe("vkr");
    expect(data?.state).toBe("head");
    expect(data?.inputs.staffing).toBe("team2");
    // Ветки и проверки дорогие: без include их нет.
    expect(data?.branches).toBeNull();
    expect(data?.checks).toBeNull();
    expect(data?.documents.length).toBeGreaterThan(10);
  });

  it("вводные версии разбираются строгой схемой", async () => {
    const { Wrapper } = wrapper();
    const { result } = renderHook(
      () => usePackOutcomeInputs(WS, REF, "work_tree"),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.version).toBe("2026.1.2");
    expect(result.current.data?.inputs.map((i) => i.id)).toContain("kind");
  });

  it("сценарии шаблона: битый виден с причиной", async () => {
    const { Wrapper } = wrapper();
    const { result } = renderHook(
      () => usePackScenarios(WS, "hse-cs-sse", "coursework"),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const broken = result.current.data?.scenarios.filter((s) => s.error);
    expect(broken).toHaveLength(1);
  });

  it("версия не выбрана: запрос не уходит", () => {
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => usePackOutcome(WS, null, {}), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("сбой сервера приходит ошибкой с кодом", async () => {
    outcomeReference.setBehavior("unreadable");
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => usePackOutcome(WS, REF, {}), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).code).toBe("version_unreadable");
  });

  it("ключ кэша не зависит от порядка вводных", () => {
    const a = packOutcomeKeys.result(WS, REF, {
      inputs: { b: "2", a: "1" },
      include: ["checks", "branches"],
    });
    const b = packOutcomeKeys.result(WS, REF, {
      state: "work_tree",
      inputs: { a: "1", b: "2" },
      include: ["branches", "checks"],
    });
    expect(a).toEqual(b);
  });

  it("пустые части запроса отбрасываются", () => {
    expect(
      normalizeOutcomeRequest({ scenario: "", example: null, inputs: {} }),
    ).toEqual({ state: "work_tree" });
  });

  it("повторяются только сбой сети и 5xx", () => {
    const api = (status: number) => new ApiError("x", "x", status);
    expect(retryOutcome(0, api(0))).toBe(true);
    expect(retryOutcome(0, api(503))).toBe(true);
    expect(retryOutcome(0, api(422))).toBe(false);
    expect(retryOutcome(1, api(503))).toBe(false);
  });

  describe("запись, удаление и прогон сценариев", () => {
    const SCENARIO = {
      format: 1 as const,
      name: { ru: "Новый" },
      inputs: { supervisor: "none" },
    };

    it("создание без If-Match, правка с If-Match, список обновляется сразу", async () => {
      const { Wrapper } = wrapper();
      const { result } = renderHook(
        () => ({
          list: usePackScenarios(WS, "hse-cs-sse", "coursework"),
          write: useWritePackScenario(WS, "hse-cs-sse", "coursework"),
        }),
        { wrapper: Wrapper },
      );
      await waitFor(() => {
        expect(result.current.list.isSuccess).toBe(true);
      });
      const created = await result.current.write.mutateAsync({
        scenario: "fresh",
        body: { scenario: SCENARIO },
        ifMatch: null,
      });
      expect(created.id).toBe("fresh");
      await waitFor(() => {
        expect(result.current.list.data?.scenarios.map((s) => s.id)).toContain(
          "fresh",
        );
      });
      const edited = await result.current.write.mutateAsync({
        scenario: "fresh",
        body: { scenario: { ...SCENARIO, name: { ru: "Правка" } } },
        ifMatch: created.etag,
      });
      expect(edited.scenario?.name.ru).toBe("Правка");
      expect(edited.etag).not.toBe(created.etag);
    });

    it("запись поверх существующего без If-Match: scenario_taken", async () => {
      const { Wrapper } = wrapper();
      const { result } = renderHook(
        () => useWritePackScenario(WS, "hse-cs-sse", "coursework"),
        { wrapper: Wrapper },
      );
      await expect(
        result.current.mutateAsync({
          scenario: "company-supervisor",
          body: { scenario: SCENARIO },
          ifMatch: null,
        }),
      ).rejects.toMatchObject({ code: "scenario_taken", status: 409 });
    });

    it("чужая правка: PackStaleFileError с ETag с диска", async () => {
      const { Wrapper } = wrapper();
      const { result } = renderHook(
        () => useWritePackScenario(WS, "hse-cs-sse", "coursework"),
        { wrapper: Wrapper },
      );
      scenarioReference.touch("company-supervisor");
      const error = await result.current
        .mutateAsync({
          scenario: "company-supervisor",
          body: { scenario: SCENARIO },
          ifMatch: '"old"',
        })
        .catch((e: unknown) => e);
      expect(error).toBeInstanceOf(PackStaleFileError);
      expect((error as PackStaleFileError).diskEtag).toBe('"ref-1"');
    });

    it("record_snapshot заменяет снимок; нет файла при If-Match: scenario_not_found", async () => {
      const { Wrapper } = wrapper();
      const { result } = renderHook(
        () => useWritePackScenario(WS, "hse-cs-sse", "coursework"),
        { wrapper: Wrapper },
      );
      const saved = await result.current.mutateAsync({
        scenario: "snap",
        body: { scenario: SCENARIO, record_snapshot: "work_tree" },
        ifMatch: null,
      });
      expect(saved.scenario?.snapshot?.documents).toBeDefined();
      await expect(
        result.current.mutateAsync({
          scenario: "ghost",
          body: { scenario: SCENARIO },
          ifMatch: '"x"',
        }),
      ).rejects.toMatchObject({ code: "scenario_not_found" });
    });

    it("удаление убирает запись из списка; отмена пишет те же данные без If-Match", async () => {
      const { Wrapper } = wrapper();
      const { result } = renderHook(
        () => ({
          list: usePackScenarios(WS, "hse-cs-sse", "coursework"),
          write: useWritePackScenario(WS, "hse-cs-sse", "coursework"),
          del: useDeletePackScenario(WS, "hse-cs-sse", "coursework"),
        }),
        { wrapper: Wrapper },
      );
      await waitFor(() => {
        expect(result.current.list.isSuccess).toBe(true);
      });
      const entry = result.current.list.data?.scenarios.find(
        (s) => s.id === "no-supervisor",
      );
      if (!entry?.scenario) throw new Error("fixture");
      await result.current.del.mutateAsync({
        scenario: "no-supervisor",
        ifMatch: entry.etag,
      });
      await waitFor(() => {
        expect(
          result.current.list.data?.scenarios.some(
            (s) => s.id === "no-supervisor",
          ),
        ).toBe(false);
      });
      const restored = await result.current.write.mutateAsync({
        scenario: "no-supervisor",
        body: { scenario: entry.scenario },
        ifMatch: null,
      });
      expect(restored.scenario).toEqual(entry.scenario);
    });

    it("прогон ждёт revision вводных, потом отдаёт статусы и итог", async () => {
      const { Wrapper } = wrapper();
      const { result, rerender } = renderHook(
        ({ revision }) => usePackScenarioRun(WS, REF2, "work_tree", revision),
        {
          wrapper: Wrapper,
          initialProps: { revision: undefined as string | undefined },
        },
      );
      expect(result.current.fetchStatus).toBe("idle");
      rerender({ revision: "rev-1" });
      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });
      expect(result.current.data?.version).toBe("2026.1.6");
      expect(result.current.data?.passed).toBe(2);
      expect(result.current.data?.failed).toBe(1);
    });

    it("ключ прогона зависит от версии, состояния и ревизии", () => {
      expect(packOutcomeKeys.scenarioRun(WS, REF2, "head", "a")).not.toEqual(
        packOutcomeKeys.scenarioRun(WS, REF2, "work_tree", "a"),
      );
      expect(packOutcomeKeys.scenarioRun(WS, REF2, "head", "a")).not.toEqual(
        packOutcomeKeys.scenarioRun(WS, REF2, "head", "b"),
      );
    });
  });
});

describe("«Почему?»: запрос, повтор и 304", () => {
  beforeAll(() => {
    installOutcomeReference();
  });
  beforeEach(() => {
    outcomeReference.setSource("reference");
    setExplainBehavior("normal");
  });
  afterEach(() => {
    setExplainBehavior("normal");
    vi.restoreAllMocks();
  });

  const element = { section: "documents", id: "operator_manual" } as const;

  it("хук отдаёт разобранный ответ на эталоне", async () => {
    const { Wrapper } = wrapper();
    const { result } = renderHook(
      () => usePackOutcomeExplain(WS, REF, { element }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.state).toBe("inactive");
    expect(result.current.data?.chain).toHaveLength(4);
  });

  it("ключ кэша не зависит от порядка вводных и пустых частей", () => {
    expect(
      packOutcomeKeys.explain(WS, REF, {
        element,
        inputs: { b: "2", a: "1" },
        scenario: null,
      }),
    ).toEqual(
      packOutcomeKeys.explain(WS, REF, {
        state: "work_tree",
        element,
        inputs: { a: "1", b: "2" },
      }),
    );
  });

  it("404 не повторяется, ошибка опознаётся как исчезнувший элемент", async () => {
    setExplainBehavior("gone");
    const { Wrapper } = wrapper();
    const { result } = renderHook(
      () => usePackOutcomeExplain(WS, REF, { element }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(isElementGone(result.current.error)).toBe(true);
    expect(isOutcomeBusy(result.current.error)).toBe(false);
    expect(result.current.failureCount).toBe(1);
  });

  it("503 outcome_busy повторяется по retry_after_s и заканчивается ответом", async () => {
    setExplainBehavior("busy");
    const { Wrapper } = wrapper();
    const { result } = renderHook(
      () => usePackOutcomeExplain(WS, REF, { element }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.element).toEqual(element);
  });

  it("опознание занятого сервера и срок ожидания", () => {
    const busy = new ApiError("busy", "outcome_busy", 503, {
      reason: "timeout",
      retry_after_s: 3,
    });
    expect(isOutcomeBusy(busy)).toBe(true);
    expect(busyDelaySeconds(busy)).toBe(3);
    expect(
      busyDelaySeconds(
        new ApiError("busy", "outcome_busy", 503, { retry_after_s: 99 }),
      ),
    ).toBe(10);
    expect(busyDelaySeconds(new ApiError("busy", "outcome_busy", 503))).toBe(1);
    expect(isOutcomeBusy(new ApiError("x", "internal_error", 503))).toBe(false);
    expect(isElementGone(new Error("x"))).toBe(false);
    // Занятый сервер повторяется, 404 нет.
    expect(
      retryOutcome(0, new ApiError("x", "outcome_element_not_found", 404)),
    ).toBe(false);
  });

  it("повторный запрос идёт с If-None-Match, на 304 возвращается прежний ответ", async () => {
    const body = {
      element,
      state: "active",
      chain: [],
      readers: [],
      counterfactuals: [],
    };
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValueOnce({
        status: 200,
        data: body,
        headers: { etag: '"abc"' },
      })
      .mockResolvedValueOnce({ status: 304, data: "", headers: {} });
    const first = await packOutcomeApi.explain(WS, REF, { element });
    expect(first).toEqual({ data: body, etag: '"abc"' });
    expect(post.mock.calls[0]?.[2]?.headers).toEqual({});
    const second = await packOutcomeApi.explain(WS, REF, { element }, first);
    expect(second).toBe(first);
    expect(post.mock.calls[1]?.[2]?.headers).toEqual({
      "If-None-Match": '"abc"',
    });
    expect(post.mock.calls[1]?.[0]).toContain("/outcome/explain");
  });

  it("ответ, не прошедший схему, не принимается", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      status: 200,
      data: { element, state: "active" },
      headers: {},
    });
    await expect(
      packOutcomeApi.explain(WS, REF, { element }),
    ).rejects.toThrow();
  });
});
