import { useQuery } from "@tanstack/react-query";
import { apiClient, parseResp } from "@shared/api";
import {
  LocalStudioInfoSchema,
  type LocalStudioInfo,
} from "../model/localStudio.schema";

export const localStudioApi = {
  info: (): Promise<LocalStudioInfo> =>
    apiClient
      .get("/local-studio", { silentError: true })
      .then(parseResp(LocalStudioInfoSchema)),
};

export const localStudioKeys = {
  info: () => ["local-studio", "info"] as const,
};

/** Адрес и версия этого сервера, откуда ставить локальную Студию (только сервер). */
export const useLocalStudioInfo = (enabled = true) =>
  useQuery({
    queryKey: localStudioKeys.info(),
    queryFn: localStudioApi.info,
    enabled,
    staleTime: 5 * 60_000,
  });
