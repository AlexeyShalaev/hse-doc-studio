import type { ReactNode } from "react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { packStudioApi } from "./packStudioApi";
import { packStudioKeys, usePackWorkspace } from "./queries";
import type { PackWorkspace } from "./schemas";

// «Обновить» идёт в фоне и может перемотать дерево пространства без ветки на свежую
// базу: когда операция кончилась (busy стал false), дерево, git и файлы читаются заново.

const FIXTURE = join(
  import.meta.dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "contracts",
  "pack-studio",
  "fixtures",
  "PackWorkspace",
  "git_ready.json",
);
const READY = JSON.parse(readFileSync(FIXTURE, "utf8")) as PackWorkspace;
const ID = READY.id;

const setup = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const scope = packStudioKeys.workspace(ID);
  client.setQueryData(packStudioKeys.tree(ID), { packs: [] });
  client.setQueryData(packStudioKeys.git(ID), { branch: null });
  client.setQueryData([...scope, "file", "demo/pack.yaml"], "id: demo");
  return { client, Wrapper };
};

const invalidated = (client: QueryClient, key: readonly unknown[]) =>
  client.getQueryState(key)?.isInvalidated ?? false;

describe("карточка пространства после фоновой операции", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("busy стал false: дерево, git и открытые файлы читаются заново", async () => {
    const { client, Wrapper } = setup();
    client.setQueryData(packStudioKeys.workspace(ID), { ...READY, busy: true });
    vi.spyOn(packStudioApi, "workspace").mockResolvedValue(READY);

    const { result } = renderHook(() => usePackWorkspace(ID), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.data?.busy).toBe(false);
    });

    expect(invalidated(client, packStudioKeys.tree(ID))).toBe(true);
    expect(invalidated(client, packStudioKeys.git(ID))).toBe(true);
    expect(
      invalidated(client, [
        ...packStudioKeys.workspace(ID),
        "file",
        "demo/pack.yaml",
      ]),
    ).toBe(true);
  });

  it("операции не было: кэш дерева и файлов не трогается", async () => {
    const { client, Wrapper } = setup();
    const workspace = vi
      .spyOn(packStudioApi, "workspace")
      .mockResolvedValue(READY);

    const { result } = renderHook(() => usePackWorkspace(ID), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(workspace).toHaveBeenCalledTimes(1);
    expect(invalidated(client, packStudioKeys.tree(ID))).toBe(false);
    expect(invalidated(client, packStudioKeys.git(ID))).toBe(false);
  });
});
