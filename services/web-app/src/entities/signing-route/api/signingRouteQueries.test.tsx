import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { signatureKeys } from "@entities/signature";
import {
  SIGNING_ROUTE_POLL_MS,
  signingRouteKeys,
  useApproveSigningTask,
  useCancelSigningRoute,
  useCreateSigningRoute,
  useMySigningTasks,
  useSendSigningRoute,
  useSigningRoute,
  useSigningRoutePreview,
  useSigningRoutes,
  useSigningTask,
  useUpdateSigningRoute,
} from "./signingRouteQueries";
import { signingRouteApi } from "./signingRouteApi";
import { createSigningRouteDemo, type SigningDemoUser } from "../testing";
import type { SigningRoute, SigningTask } from "../model/signingRoute.schema";

// Настоящие хуки сущности поверх моков контракта: так экраны W2–W6 и будут работать без бэкенда.

const PROJECT = "p_01hxa1c4de";
const PROFILE = "topic-approval";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };
const SUPERVISOR: SigningDemoUser = {
  id: "u_demo_petrov",
  name: "Петров П. П.",
};

let me: SigningDemoUser = AUTHOR;
const demo = createSigningRouteDemo({ getUser: () => me });

const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } });

const wrap =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

/** Автор отправил черновик точки; возвращает id маршрута. */
const sendRoute = async (): Promise<string> => {
  me = AUTHOR;
  const route = await signingRouteApi.create(PROJECT, PROFILE);
  const preview = await signingRouteApi.preview(PROJECT, route.id);
  await signingRouteApi.send(PROJECT, route.id, {
    expected: { topic_application: preview.docs[0]?.token ?? "" },
    sign: null,
  });
  return route.id;
};

beforeAll(() => {
  installDemoAdapter(apiClient, createDemoRouter(demo.routes));
});

beforeEach(() => {
  demo.reset();
  me = AUTHOR;
});

describe("хуки автора", () => {
  it("создание кладёт маршрут в кэш, правка пересчитывает предпросмотр", async () => {
    const client = makeClient();
    const { result } = renderHook(() => useCreateSigningRoute(PROJECT), {
      wrapper: wrap(client),
    });
    let routeId = "";
    await act(async () => {
      routeId = (await result.current.mutateAsync(PROFILE)).id;
    });
    expect(
      client.getQueryData(signingRouteKeys.route(PROJECT, routeId)),
    ).toMatchObject({ id: routeId, status: "draft" });

    const view = renderHook(
      () => ({
        route: useSigningRoute(PROJECT, routeId),
        preview: useSigningRoutePreview(PROJECT, routeId),
        update: useUpdateSigningRoute(PROJECT, routeId),
      }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => {
      expect(view.result.current.preview.data?.can_send).toBe(true);
    });
    const route = view.result.current.route.data;
    if (!route) throw new Error("route not loaded");
    await act(async () => {
      await view.result.current.update.mutateAsync({
        steps: [
          ...route.steps.map((step) =>
            step.map((p) => ({
              id: p.id,
              persona: p.persona,
              user_id: p.user_id,
              invitation_id: p.invitation_id,
            })),
          ),
          [
            {
              id: null,
              persona: "academic_supervisor",
              user_id: null,
              invitation_id: null,
            },
          ],
        ],
        extra_slots: [
          { doc_id: "topic_application", slot_id: "academic_supervisor" },
        ],
        deadline: null,
        message: null,
      });
    });
    // Ответ PUT сразу в кэше, без повторного GET.
    expect(
      client.getQueryData<SigningRoute>(
        signingRouteKeys.route(PROJECT, routeId),
      )?.steps,
    ).toHaveLength(3);
    await waitFor(() => {
      expect(view.result.current.route.data?.steps).toHaveLength(3);
    });
    await waitFor(() => {
      expect(view.result.current.preview.data?.can_send).toBe(false);
    });
  });

  it("неудачная отправка перечитывает маршрут и отдаёт код ошибки", async () => {
    const client = makeClient();
    const route = await signingRouteApi.create(PROJECT, PROFILE);
    const { result } = renderHook(
      () => ({
        route: useSigningRoute(PROJECT, route.id),
        send: useSendSigningRoute(PROJECT, route.id),
      }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => {
      expect(result.current.route.data?.status).toBe("draft");
    });
    const updatedAt = result.current.route.dataUpdatedAt;
    let error: unknown = null;
    await act(async () => {
      try {
        await result.current.send.mutateAsync({
          expected: { topic_application: "build:old" },
          sign: null,
        });
      } catch (e) {
        error = e;
      }
    });
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("doc_changed");
    await waitFor(() => {
      expect(result.current.route.dataUpdatedAt).toBeGreaterThan(updatedAt);
    });
  });

  it("активный маршрут перечитывается, отменённый нет", async () => {
    const client = makeClient();
    const routeId = await sendRoute();
    const { result } = renderHook(
      () => ({
        list: useSigningRoutes(PROJECT, PROFILE),
        route: useSigningRoute(PROJECT, routeId),
        cancel: useCancelSigningRoute(PROJECT, routeId),
      }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => {
      expect(result.current.route.data?.status).toBe("active");
    });
    const interval = () =>
      client
        .getQueryCache()
        .find({ queryKey: signingRouteKeys.route(PROJECT, routeId) })
        ?.observers[0]?.options.refetchInterval;
    const query = client
      .getQueryCache()
      .find({ queryKey: signingRouteKeys.route(PROJECT, routeId) });
    const poll = (): unknown => {
      const option = interval();
      return typeof option === "function" && query
        ? option(query as never)
        : option;
    };
    expect(poll()).toBe(SIGNING_ROUTE_POLL_MS);

    await act(async () => {
      await result.current.cancel.mutateAsync();
    });
    await waitFor(() => {
      expect(result.current.route.data?.status).toBe("cancelled");
    });
    expect(poll()).toBe(false);
    await waitFor(() => {
      expect(result.current.list.data?.items[0]?.status).toBe("cancelled");
    });
  });
});

describe("хуки подписанта", () => {
  it("согласие обновляет задачу из ответа и перечитывает «На подпись» и подписи", async () => {
    const routeId = await sendRoute();
    me = SUPERVISOR;
    const client = makeClient();
    client.setQueryData(signatureKeys.state(PROJECT), { slots: {} });
    const { result } = renderHook(
      () => ({
        task: useSigningTask(PROJECT, routeId),
        mine: useMySigningTasks(),
        approve: useApproveSigningTask(PROJECT, routeId),
      }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => {
      expect(result.current.mine.data?.items).toHaveLength(1);
    });
    await waitFor(() => {
      expect(result.current.task.data?.me.next_action).toBe("approve_and_sign");
    });
    const task = result.current.task.data;
    if (!task) throw new Error("task not loaded");
    await act(async () => {
      await result.current.approve.mutateAsync({
        expected: Object.fromEntries(
          task.docs.map((d) => [d.doc_id, d.token ?? ""]),
        ),
        method: null,
        sign: { identity_id: null, passphrase: null },
      });
    });
    expect(
      client.getQueryData<SigningTask>(signingRouteKeys.task(PROJECT, routeId))
        ?.me.state,
    ).toBe("done");
    expect(
      client.getQueryState(signatureKeys.state(PROJECT))?.isInvalidated,
    ).toBe(true);
    await waitFor(() => {
      expect(result.current.mine.data?.items).toEqual([]);
    });
  });

  it("не участнику задача отвечает 404 без повторов", async () => {
    const routeId = await sendRoute();
    me = { id: "u_stranger", name: "Чужой" };
    const client = new QueryClient();
    const { result } = renderHook(() => useSigningTask(PROJECT, routeId), {
      wrapper: wrap(client),
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect((result.current.error as ApiError).status).toBe(404);
    expect(result.current.failureCount).toBe(1);
  });

  it("пустые id не делают запросов", () => {
    const client = makeClient();
    const { result } = renderHook(
      () => ({
        route: useSigningRoute(PROJECT, ""),
        task: useSigningTask("", "sr"),
        list: useSigningRoutes("", null),
      }),
      { wrapper: wrap(client) },
    );
    expect(result.current.route.fetchStatus).toBe("idle");
    expect(result.current.task.fetchStatus).toBe("idle");
    expect(result.current.list.fetchStatus).toBe("idle");
  });
});
