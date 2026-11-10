import { apiClient, parseResp } from "@shared/api";
import {
  SigningLinkSchema,
  SigningReminderSchema,
  SigningRouteListSchema,
  SigningRoutePreviewSchema,
  SigningRouteSchema,
  SigningTaskListSchema,
  SigningTaskSchema,
  type ApproveSigningTaskRequest,
  type ReturnSigningTaskRequest,
  type SendSigningRouteRequest,
  type SignSigningTaskRequest,
  type SigningLink,
  type SigningReminder,
  type SigningRoute,
  type SigningRouteList,
  type SigningRoutePreview,
  type SigningTask,
  type SigningTaskList,
  type UpdateSigningRouteRequest,
} from "../model/signingRoute.schema";

// Ошибки показывают сами экраны (по коду из тела), общий тост клиента лишний.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;
const routes = (projectId: string) =>
  `/projects/${enc(projectId)}/signing-routes`;
const route = (projectId: string, routeId: string) =>
  `${routes(projectId)}/${enc(routeId)}`;
const task = (projectId: string, routeId: string) =>
  `${route(projectId, routeId)}/task`;
const withSignal = (signal?: AbortSignal) => (signal ? { signal } : {});
// FormData: границу multipart ставит браузер, иначе тело уйдёт как application/json.
const multipart = { ...quiet, headers: { "Content-Type": null } };

/** Маршрут глазами автора: черновик, правка, предпросмотр, отправка, отмена (раздел 8). */
export const signingRouteApi = {
  list: (
    projectId: string,
    profileId: string | null,
    signal?: AbortSignal,
  ): Promise<SigningRouteList> =>
    apiClient
      .get(routes(projectId), {
        ...quiet,
        params: profileId === null ? {} : { profile_id: profileId },
        ...withSignal(signal),
      })
      .then(parseResp(SigningRouteListSchema)),
  /** Черновик точки: существующий незавершённый маршрут или новый из пака. */
  create: (projectId: string, profileId: string): Promise<SigningRoute> =>
    apiClient
      .post(routes(projectId), { profile_id: profileId }, quiet)
      .then(parseResp(SigningRouteSchema)),
  get: (
    projectId: string,
    routeId: string,
    signal?: AbortSignal,
  ): Promise<SigningRoute> =>
    apiClient
      .get(route(projectId, routeId), { ...quiet, ...withSignal(signal) })
      .then(parseResp(SigningRouteSchema)),
  update: (
    projectId: string,
    routeId: string,
    body: UpdateSigningRouteRequest,
  ): Promise<SigningRoute> =>
    apiClient
      .put(route(projectId, routeId), body, quiet)
      .then(parseResp(SigningRouteSchema)),
  /** Что будет при отправке сохранённого маршрута; ничего не меняет. */
  preview: (
    projectId: string,
    routeId: string,
    signal?: AbortSignal,
  ): Promise<SigningRoutePreview> =>
    apiClient
      .post(
        `${route(projectId, routeId)}/preview`,
        {},
        { ...quiet, ...withSignal(signal) },
      )
      .then(parseResp(SigningRoutePreviewSchema)),
  /**
   * «Отправить», «Отправить заново» и «Отправить новую версию» (12.6). Пустое «Что изменилось»
   * не уходит вовсе: сервер до среза R16 поля `note` не знает и отверг бы запрос.
   */
  send: (
    projectId: string,
    routeId: string,
    { note, ...body }: SendSigningRouteRequest,
  ): Promise<SigningRoute> =>
    apiClient
      .post(
        `${route(projectId, routeId)}/send`,
        note?.trim() ? { ...body, note: note.trim() } : body,
        quiet,
      )
      .then(parseResp(SigningRouteSchema)),
  cancel: (projectId: string, routeId: string): Promise<SigningRoute> =>
    apiClient
      .post(`${route(projectId, routeId)}/cancel`, {}, quiet)
      .then(parseResp(SigningRouteSchema)),
  /** Снять завершённый маршрут с контроля. */
  archive: (projectId: string, routeId: string): Promise<SigningRoute> =>
    apiClient
      .post(`${route(projectId, routeId)}/archive`, {}, quiet)
      .then(parseResp(SigningRouteSchema)),
  remind: (
    projectId: string,
    routeId: string,
    participantId: string,
  ): Promise<SigningReminder> =>
    apiClient
      .post(
        `${route(projectId, routeId)}/participants/${enc(participantId)}/remind`,
        {},
        quiet,
      )
      .then(parseResp(SigningReminderSchema)),
  /**
   * Ссылка, которую автор сам перешлёт подписанту: страница подписи или новая ссылка
   * приглашения. Не напоминание: пауз нет, в маршрут ничего не пишется.
   */
  link: (
    projectId: string,
    routeId: string,
    participantId: string,
  ): Promise<SigningLink> =>
    apiClient
      .post(
        `${route(projectId, routeId)}/participants/${enc(participantId)}/link`,
        {},
        quiet,
      )
      .then(parseResp(SigningLinkSchema)),
};

/** Задача подписанта на странице `/sign/:projectId/:routeId`: только участнику маршрута. */
export const signingTaskApi = {
  get: (
    projectId: string,
    routeId: string,
    signal?: AbortSignal,
  ): Promise<SigningTask> =>
    apiClient
      .get(task(projectId, routeId), { ...quiet, ...withSignal(signal) })
      .then(parseResp(SigningTaskSchema)),
  approve: (
    projectId: string,
    routeId: string,
    body: ApproveSigningTaskRequest,
  ): Promise<SigningTask> =>
    apiClient
      .post(`${task(projectId, routeId)}/approve`, body, quiet)
      .then(parseResp(SigningTaskSchema)),
  sign: (
    projectId: string,
    routeId: string,
    body: SignSigningTaskRequest,
  ): Promise<SigningTask> =>
    apiClient
      .post(`${task(projectId, routeId)}/sign`, body, quiet)
      .then(parseResp(SigningTaskSchema)),
  /** Вернуть на доработку: комментарий обязателен. */
  returnForRework: (
    projectId: string,
    routeId: string,
    body: ReturnSigningTaskRequest,
  ): Promise<SigningTask> =>
    apiClient
      .post(`${task(projectId, routeId)}/return`, body, quiet)
      .then(parseResp(SigningTaskSchema)),
  /** Своя картинка (загруженная или нарисованная, PNG); `remember` сохраняет её в профиль. */
  uploadImage: (
    projectId: string,
    routeId: string,
    file: Blob,
    remember: boolean,
  ): Promise<SigningTask> => {
    const form = new FormData();
    form.append("file", file);
    form.append("remember", remember ? "true" : "false");
    return apiClient
      .post(`${task(projectId, routeId)}/image`, form, multipart)
      .then(parseResp(SigningTaskSchema));
  },
  /** Данные плашки из своего ключа Студии. */
  setPlateKey: (
    projectId: string,
    routeId: string,
    identityId: string,
  ): Promise<SigningTask> =>
    apiClient
      .put(
        `${task(projectId, routeId)}/plate`,
        { identity_id: identityId },
        quiet,
      )
      .then(parseResp(SigningTaskSchema)),
  /** Данные плашки из сертификата или открытого ключа файлом. */
  setPlateFile: (
    projectId: string,
    routeId: string,
    file: File,
  ): Promise<SigningTask> => {
    const form = new FormData();
    form.append("file", file);
    return apiClient
      .post(`${task(projectId, routeId)}/plate/file`, form, multipart)
      .then(parseResp(SigningTaskSchema));
  },
};

/** «На подпись»: мои задачи по всем проектам. */
export const accountSigningApi = {
  tasks: (signal?: AbortSignal): Promise<SigningTaskList> =>
    apiClient
      .get("/account/signing-tasks", { ...quiet, ...withSignal(signal) })
      .then(parseResp(SigningTaskListSchema)),
};
