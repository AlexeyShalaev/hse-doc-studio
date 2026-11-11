import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, adminClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import {
  LIFECYCLE_SWEEP_CONTRACT_SCHEMAS,
  type LifecycleSweep,
} from "@entities/session";
import { lifecycleApi } from "./lifecycleApi";
import {
  lifecycleKeys,
  useCancelSweep,
  useLifecycleSweep,
  useStartSweep,
  useSweepPreview,
} from "./lifecycleQueries";
import { opsKeys } from "./opsQueries";
import {
  LIFECYCLE_SWEEP_CONTRACT_EXAMPLES,
  SWEEP_SOURCE_KEYS,
  SWEEP_STATES,
  createLifecycleSweepDemo,
  type SweepDemoProfile,
} from "../testing";

// «Освободить место» (storage-cleanup.md, 9.2): эталоны, моки и хуки. Срез B7 перенесёт эталоны в
// contracts/server/fixtures, и проверка станет общей с бэкендом.

const examples = Object.entries(LIFECYCLE_SWEEP_CONTRACT_EXAMPLES).flatMap(
  ([schema, variants]) =>
    Object.entries(variants).map(
      ([name, body]) => [`${schema}/${name}`, schema, body] as const,
    ),
);

describe("контракт «Освободить место»: эталоны", () => {
  it("у каждой схемы есть эталон, у каждого эталона схема", () => {
    expect(Object.keys(LIFECYCLE_SWEEP_CONTRACT_EXAMPLES).sort()).toEqual(
      Object.keys(LIFECYCLE_SWEEP_CONTRACT_SCHEMAS).sort(),
    );
  });

  it.each(examples)("%s разбирается zod без потерь", (_label, schema, body) => {
    const parsed = LIFECYCLE_SWEEP_CONTRACT_SCHEMAS[schema]?.safeParse(body);
    expect(parsed?.success).toBe(true);
    expect(parsed?.data).toEqual(body);
  });

  it.each(examples)("%s: лишнее поле отвергается", (_label, schema, body) => {
    const extra = { ...(body as Record<string, unknown>), surprise: 1 };
    expect(
      LIFECYCLE_SWEEP_CONTRACT_SCHEMAS[schema]?.safeParse(extra).success,
    ).toBe(false);
  });

  it.each(Object.entries(SWEEP_STATES))(
    "состояние галереи %s проходит схему",
    (_id, sweep) => {
      expect(
        LIFECYCLE_SWEEP_CONTRACT_SCHEMAS.LifecycleSweep?.parse(sweep),
      ).toEqual(sweep);
    },
  );
});

let profile: SweepDemoProfile = "default";
let admin = true;
const demo = createLifecycleSweepDemo({
  getActor: () => ({ id: "u_admin", name: "Админ", admin }),
  profile: () => profile,
});

const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrap =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
const codeOf = async (promise: Promise<unknown>): Promise<string | null> => {
  try {
    await promise;
    return null;
  } catch (error) {
    return error instanceof ApiError ? error.code : String(error);
  }
};

beforeAll(() => {
  installDemoAdapter(adminClient, createDemoRouter(demo.routes));
});

beforeEach(() => {
  demo.reset();
  profile = "default";
  admin = true;
});

describe("API «Освободить место» на моках", () => {
  it("прогон идёт по источникам реестра, после него предпросмотр «нечего»", async () => {
    const preview = await lifecycleApi.sweepPreview();
    expect(preview.nothing).toBe(false);
    expect(preview.sources.map((s) => s.key)).toEqual([...SWEEP_SOURCE_KEYS]);
    expect(await lifecycleApi.sweep()).toBeNull();

    const started = await lifecycleApi.startSweep();
    expect(started.status).toBe("running");
    expect(await codeOf(lifecycleApi.startSweep())).toBe(
      "lifecycle_sweep_busy",
    );
    let sweep: LifecycleSweep | null = started;
    for (let i = 0; i < 10 && sweep?.status === "running"; i += 1) {
      sweep = await lifecycleApi.sweep();
    }
    expect(sweep?.status).toBe("done");
    expect(sweep?.steps.every((s) => s.status === "done")).toBe(true);
    expect(sweep?.removed_total).toBe(
      preview.sources.reduce((a, s) => a + (s.count ?? 0), 0),
    );
    expect(sweep?.freed_bytes).toBeGreaterThan(0);
    expect((await lifecycleApi.sweepPreview()).nothing).toBe(true);
  });

  it("остановка после текущего источника, повторная даёт command_finished", async () => {
    const started = await lifecycleApi.startSweep();
    expect((await lifecycleApi.cancelSweep(started.id)).status).toBe(
      "cancelling",
    );
    const sweep = await lifecycleApi.sweep();
    expect(sweep?.status).toBe("cancelled");
    expect(sweep?.steps.map((s) => s.status).slice(0, 2)).toEqual([
      "done",
      "skipped",
    ]);
    expect(await codeOf(lifecycleApi.cancelSweep(started.id))).toBe(
      "command_finished",
    );
    expect(await codeOf(lifecycleApi.cancelSweep("lsw_unknown"))).toBe(
      "not_found",
    );
  });

  it("профили предпросмотра и прерванный прошлый прогон", async () => {
    profile = "capped";
    const capped = await lifecycleApi.sweepPreview();
    expect(capped.sources.some((s) => s.capped)).toBe(true);
    expect(capped.sources.some((s) => s.count === null)).toBe(true);
    profile = "nothing";
    expect((await lifecycleApi.sweepPreview()).nothing).toBe(true);
    demo.seed(SWEEP_STATES.interrupted);
    expect((await lifecycleApi.sweep())?.status).toBe("interrupted");
  });

  it("не админу адресов нет", async () => {
    admin = false;
    expect(await codeOf(lifecycleApi.sweepPreview())).toBe("not_found");
  });
});

describe("хуки «Освободить место»", () => {
  it("запуск кладёт прогон в кэш, итог перечитывает «Хранение данных» и «Хранилище»", async () => {
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(
      () => ({
        sweep: useLifecycleSweep(),
        start: useStartSweep(),
        cancel: useCancelSweep(),
      }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => {
      expect(result.current.sweep.isSuccess).toBe(true);
    });
    expect(result.current.sweep.data).toBeNull();
    await act(async () => {
      await result.current.start.mutateAsync();
    });
    await waitFor(() => {
      expect(result.current.sweep.data?.status).toBe("running");
    });
    for (let i = 0; i < 10; i += 1) {
      await act(async () => {
        await client.refetchQueries({ queryKey: lifecycleKeys.sweep });
      });
    }
    expect(result.current.sweep.data?.status).toBe("done");
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: lifecycleKeys.overview,
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: opsKeys.storage });
  });

  it("предпросмотр читается только при открытом диалоге", async () => {
    const client = makeClient();
    const closed = renderHook(() => useSweepPreview({ enabled: false }), {
      wrapper: wrap(client),
    });
    expect(closed.result.current.fetchStatus).toBe("idle");
    const open = renderHook(() => useSweepPreview(), {
      wrapper: wrap(client),
    });
    await waitFor(() => {
      expect(open.result.current.data?.nothing).toBe(false);
    });
  });
});
