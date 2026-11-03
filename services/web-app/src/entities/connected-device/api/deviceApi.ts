import { apiClient, parseResp } from "@shared/api";
import {
  AccountDevicesSchema,
  LocalDeviceSchema,
  ProjectStudiosSchema,
  StudioLinkSchema,
  type AccountDevices,
  type LocalDevice,
  type ProjectStudios,
  type StudioLink,
} from "../model/device.schema";

// Ошибки показывает панель сама (строка «нет связи» вместо общего тоста клиента).
const quiet = { silentError: true } as const;

/** Облако: свои устройства и Студии проекта (`/account/devices`, `/projects/{id}/studios`). */
export const deviceApi = {
  account: (): Promise<AccountDevices> =>
    apiClient
      .get("/account/devices", quiet)
      .then(parseResp(AccountDevicesSchema)),
  forget: (id: string): Promise<unknown> =>
    apiClient.delete(`/account/devices/${encodeURIComponent(id)}`),
  project: (projectId: string): Promise<ProjectStudios> =>
    apiClient
      .get(`/projects/${projectId}/studios`, quiet)
      .then(parseResp(ProjectStudiosSchema)),
};

/** Локальная Студия: имя устройства и связь с облаком (`/device`, `/git/studio-link`). */
export const studioLinkApi = {
  device: (): Promise<LocalDevice> =>
    apiClient.get("/device", quiet).then(parseResp(LocalDeviceSchema)),
  rename: (name: string | null): Promise<LocalDevice> =>
    apiClient.put("/device", { name }).then(parseResp(LocalDeviceSchema)),
  link: (projectId?: string): Promise<StudioLink> =>
    apiClient
      .get("/git/studio-link", {
        ...quiet,
        ...(projectId ? { params: { project: projectId } } : {}),
      })
      .then(parseResp(StudioLinkSchema)),
};
