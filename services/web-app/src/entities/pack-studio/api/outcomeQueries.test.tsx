import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import { installOutcomeReference, outcomeReference } from "../reference";
import {
  normalizeOutcomeRequest,
  packOutcomeKeys,
  retryOutcome,
  usePackOutcome,
  usePackOutcomeInputs,
  usePackScenarios,
} from "./outcomeQueries";

// Хуки результата на эталонах контракта: запрос уходит в транспорт axios, подмена отвечает
// эталоном со строгим разбором схемами. Тот же код, который позже получит настоящий сервер.

const REF = { pack: "hse-cs-se", template: "vkr", version: "2026.1.2" };
const WS = "ws-1";

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
  });
  afterEach(() => {
    outcomeReference.setSource("reference");
    outcomeReference.setBehavior("normal");
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
});
