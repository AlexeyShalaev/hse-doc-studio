import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { invitationKeys } from "@entities/invitation";
import { signatureKeys } from "@entities/signature";
import {
  accountSigningApi,
  signingRouteApi,
  signingTaskApi,
} from "./signingRouteApi";
import { isRouteLive } from "../lib/signingRouteStatus";
import type {
  ApproveSigningTaskRequest,
  SendSigningRouteRequest,
  SignSigningTaskRequest,
  SigningRoute,
  SigningTask,
  UpdateSigningRouteRequest,
} from "../model/signingRoute.schema";

export const signingRouteKeys = {
  all: ["signing-routes"] as const,
  project: (projectId: string) =>
    [...signingRouteKeys.all, "project", projectId] as const,
  lists: (projectId: string) =>
    [...signingRouteKeys.project(projectId), "list"] as const,
  list: (projectId: string, profileId: string | null) =>
    [...signingRouteKeys.lists(projectId), profileId ?? ""] as const,
  route: (projectId: string, routeId: string) =>
    [...signingRouteKeys.project(projectId), "route", routeId] as const,
  preview: (projectId: string, routeId: string) =>
    [...signingRouteKeys.route(projectId, routeId), "preview"] as const,
  task: (projectId: string, routeId: string) =>
    [...signingRouteKeys.route(projectId, routeId), "task"] as const,
  myTasks: () => [...signingRouteKeys.all, "my-tasks"] as const,
};

/** Активный маршрут меняют другие люди: карточка и страница подписанта перечитывают его. */
export const SIGNING_ROUTE_POLL_MS = 30_000;
/** Задачи «На подпись» перечитываются вместе со сводкой «Входящих». */
export const SIGNING_TASKS_POLL_MS = 60_000;

type QueryOptions = { enabled?: boolean };

const pollWhileLive = (status: SigningRoute["status"] | undefined) =>
  status !== undefined && isRouteLive(status) ? SIGNING_ROUTE_POLL_MS : false;

/**
 * После действия с маршрутом меняются его сводки, задачи, план подписей проекта (придержанные
 * слоты, фиксации, подписи) и счётчик «Входящих».
 */
const refreshAround = async (
  client: QueryClient,
  projectId: string,
  routeId: string,
): Promise<void> => {
  await Promise.all([
    client.invalidateQueries({ queryKey: signingRouteKeys.lists(projectId) }),
    client.invalidateQueries({
      queryKey: signingRouteKeys.preview(projectId, routeId),
    }),
    client.invalidateQueries({ queryKey: signingRouteKeys.myTasks() }),
    client.invalidateQueries({ queryKey: signatureKeys.state(projectId) }),
    client.invalidateQueries({ queryKey: invitationKeys.summary() }),
  ]);
};

/** Ответ действия автора уже содержит маршрут: кладём его в кэш, остальное перечитываем. */
const useAfterRouteChange = (projectId: string) => {
  const client = useQueryClient();
  return async (route: SigningRoute | undefined, routeId: string) => {
    if (route) {
      client.setQueryData(signingRouteKeys.route(projectId, route.id), route);
      await Promise.all([
        refreshAround(client, projectId, route.id),
        client.invalidateQueries({
          queryKey: signingRouteKeys.task(projectId, route.id),
        }),
      ]);
      return;
    }
    // Ошибка (например, 409 «документ изменился»): перечитываем всё вокруг маршрута.
    await Promise.all([
      refreshAround(client, projectId, routeId),
      client.invalidateQueries({
        queryKey: signingRouteKeys.route(projectId, routeId),
      }),
    ]);
  };
};

/** Ответ действия подписанта содержит его задачу; ход маршрута у автора перечитываем. */
const useAfterTaskChange = (projectId: string, routeId: string) => {
  const client = useQueryClient();
  return async (task: SigningTask | undefined) => {
    if (task) {
      client.setQueryData(signingRouteKeys.task(projectId, routeId), task);
    } else {
      await client.invalidateQueries({
        queryKey: signingRouteKeys.task(projectId, routeId),
      });
    }
    await Promise.all([
      refreshAround(client, projectId, routeId),
      client.invalidateQueries({
        queryKey: signingRouteKeys.route(projectId, routeId),
        exact: true,
      }),
    ]);
  };
};

// Автор

/** Маршруты точки (или всего проекта при `profileId = null`). */
export const useSigningRoutes = (
  projectId: string,
  profileId: string | null,
  { enabled = true }: QueryOptions = {},
) =>
  useQuery({
    queryKey: signingRouteKeys.list(projectId, profileId),
    queryFn: ({ signal }) => signingRouteApi.list(projectId, profileId, signal),
    enabled: enabled && projectId !== "",
    staleTime: 10_000,
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => isRouteLive(item.status))
        ? SIGNING_ROUTE_POLL_MS
        : false,
  });

export const useSigningRoute = (
  projectId: string,
  routeId: string,
  { enabled = true }: QueryOptions = {},
) =>
  useQuery({
    queryKey: signingRouteKeys.route(projectId, routeId),
    queryFn: ({ signal }) => signingRouteApi.get(projectId, routeId, signal),
    enabled: enabled && projectId !== "" && routeId !== "",
    staleTime: 5_000,
    refetchInterval: (query) => pollWhileLive(query.state.data?.status),
    retry: false,
  });

/** Предпросмотр отправки: пересчитывается после каждой правки маршрута. */
export const useSigningRoutePreview = (
  projectId: string,
  routeId: string,
  { enabled = true }: QueryOptions = {},
) =>
  useQuery({
    queryKey: signingRouteKeys.preview(projectId, routeId),
    queryFn: ({ signal }) =>
      signingRouteApi.preview(projectId, routeId, signal),
    enabled: enabled && projectId !== "" && routeId !== "",
    staleTime: 0,
    retry: false,
  });

export const useCreateSigningRoute = (projectId: string) => {
  const after = useAfterRouteChange(projectId);
  return useMutation({
    mutationFn: (profileId: string) =>
      signingRouteApi.create(projectId, profileId),
    onSuccess: (route) => after(route, route.id),
  });
};

export const useUpdateSigningRoute = (projectId: string, routeId: string) => {
  const after = useAfterRouteChange(projectId);
  return useMutation({
    mutationFn: (body: UpdateSigningRouteRequest) =>
      signingRouteApi.update(projectId, routeId, body),
    onSettled: (route) => after(route, routeId),
  });
};

export const useSendSigningRoute = (projectId: string, routeId: string) => {
  const after = useAfterRouteChange(projectId);
  return useMutation({
    mutationFn: (body: SendSigningRouteRequest) =>
      signingRouteApi.send(projectId, routeId, body),
    onSettled: (route) => after(route, routeId),
  });
};

export const useCancelSigningRoute = (projectId: string, routeId: string) => {
  const after = useAfterRouteChange(projectId);
  return useMutation({
    mutationFn: () => signingRouteApi.cancel(projectId, routeId),
    onSettled: (route) => after(route, routeId),
  });
};

/** «Пропустить» (13.6): подписи участника на точке необязательны; ответ несёт маршрут. */
export const useSkipSigningParticipant = (
  projectId: string,
  routeId: string,
) => {
  const after = useAfterRouteChange(projectId);
  return useMutation({
    mutationFn: (participantId: string) =>
      signingRouteApi.skip(projectId, routeId, participantId),
    onSettled: (route) => after(route, routeId),
  });
};

/** «Вернуть как в шаблоне» (15.6): отметки «необязательна» живут в состоянии подписей, оно тоже перечитывается. */
export const useRestoreSigningRoutePreset = (
  projectId: string,
  routeId: string,
) => {
  const after = useAfterRouteChange(projectId);
  return useMutation({
    mutationFn: () => signingRouteApi.restorePreset(projectId, routeId),
    onSettled: (route) => after(route, routeId),
  });
};

export const useArchiveSigningRoute = (projectId: string, routeId: string) => {
  const after = useAfterRouteChange(projectId);
  return useMutation({
    mutationFn: () => signingRouteApi.archive(projectId, routeId),
    onSettled: (route) => after(route, routeId),
  });
};

export const useRemindSigningParticipant = (
  projectId: string,
  routeId: string,
) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (participantId: string) =>
      signingRouteApi.remind(projectId, routeId, participantId),
    // reminded_at и счётчик напоминаний живут в ходе маршрута.
    onSettled: () =>
      client.invalidateQueries({
        queryKey: signingRouteKeys.route(projectId, routeId),
        exact: true,
      }),
  });
};

/** «Скопировать ссылку» приглашённому: новая ссылка приглашения, маршрут не меняется. */
export const useSigningParticipantLink = (projectId: string, routeId: string) =>
  useMutation({
    mutationFn: (participantId: string) =>
      signingRouteApi.link(projectId, routeId, participantId),
  });

// Подписант

export const useSigningTask = (
  projectId: string,
  routeId: string,
  { enabled = true }: QueryOptions = {},
) =>
  useQuery({
    queryKey: signingRouteKeys.task(projectId, routeId),
    queryFn: ({ signal }) => signingTaskApi.get(projectId, routeId, signal),
    enabled: enabled && projectId !== "" && routeId !== "",
    staleTime: 5_000,
    refetchInterval: (query) => pollWhileLive(query.state.data?.route.status),
    refetchOnWindowFocus: true,
    retry: false,
  });

export const useApproveSigningTask = (projectId: string, routeId: string) => {
  const after = useAfterTaskChange(projectId, routeId);
  return useMutation({
    mutationFn: (body: ApproveSigningTaskRequest) =>
      signingTaskApi.approve(projectId, routeId, body),
    onSettled: (task) => after(task),
  });
};

export const useSignSigningTask = (projectId: string, routeId: string) => {
  const after = useAfterTaskChange(projectId, routeId);
  return useMutation({
    mutationFn: (body: SignSigningTaskRequest) =>
      signingTaskApi.sign(projectId, routeId, body),
    onSettled: (task) => after(task),
  });
};

export const useReturnSigningTask = (projectId: string, routeId: string) => {
  const after = useAfterTaskChange(projectId, routeId);
  return useMutation({
    mutationFn: (comment: string) =>
      signingTaskApi.returnForRework(projectId, routeId, { comment }),
    onSettled: (task) => after(task),
  });
};

export const useUploadSigningTaskImage = (
  projectId: string,
  routeId: string,
) => {
  const after = useAfterTaskChange(projectId, routeId);
  return useMutation({
    mutationFn: (v: { file: Blob; remember: boolean }) =>
      signingTaskApi.uploadImage(projectId, routeId, v.file, v.remember),
    onSettled: (task) => after(task),
  });
};

export const useSetSigningTaskPlate = (projectId: string, routeId: string) => {
  const after = useAfterTaskChange(projectId, routeId);
  return useMutation({
    mutationFn: (source: { identityId: string } | { file: File }) =>
      "file" in source
        ? signingTaskApi.setPlateFile(projectId, routeId, source.file)
        : signingTaskApi.setPlateKey(projectId, routeId, source.identityId),
    onSettled: (task) => after(task),
  });
};

// «На подпись»

export const useMySigningTasks = ({ enabled = true }: QueryOptions = {}) =>
  useQuery({
    queryKey: signingRouteKeys.myTasks(),
    queryFn: ({ signal }) => accountSigningApi.tasks(signal),
    enabled,
    staleTime: 15_000,
    refetchInterval: SIGNING_TASKS_POLL_MS,
    refetchOnWindowFocus: true,
  });
