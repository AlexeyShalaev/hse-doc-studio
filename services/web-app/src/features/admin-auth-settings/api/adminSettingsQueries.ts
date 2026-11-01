import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sessionKeys } from "@entities/session";
import type {
  CreateAdminOidcProviderRequest,
  UpdateAdminOidcProviderRequest,
  UpdateAdminRegistrationRequest,
  UpdateAdminSmtpRequest,
} from "@entities/session";
import { adminSettingsApi } from "./adminSettingsApi";

export const adminSettingsKeys = {
  all: ["admin", "settings"] as const,
  registration: () => [...adminSettingsKeys.all, "registration"] as const,
  auth: () => [...adminSettingsKeys.all, "auth"] as const,
  smtp: () => [...adminSettingsKeys.all, "smtp"] as const,
  providers: () => [...adminSettingsKeys.all, "oidc-providers"] as const,
};

export const useRegistrationSettings = () =>
  useQuery({
    queryKey: adminSettingsKeys.registration(),
    queryFn: () => adminSettingsApi.registration(),
    staleTime: 0,
  });
export const useAuthSettings = () =>
  useQuery({
    queryKey: adminSettingsKeys.auth(),
    queryFn: () => adminSettingsApi.auth(),
    staleTime: 0,
  });
export const useSmtpSettings = () =>
  useQuery({
    queryKey: adminSettingsKeys.smtp(),
    queryFn: () => adminSettingsApi.smtp(),
    staleTime: 0,
  });

/** Экран входа читает режимы и провайдеров из bootstrap: после правки он устаревает. */
const useRefreshBootstrap = () => {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });
};

export const useUpdateRegistration = () => {
  const client = useQueryClient();
  const refresh = useRefreshBootstrap();
  return useMutation({
    mutationFn: (body: UpdateAdminRegistrationRequest) =>
      adminSettingsApi.updateRegistration(body),
    onSuccess: (data) => {
      client.setQueryData(adminSettingsKeys.registration(), data);
      void refresh();
    },
  });
};

export const useUpdateAuth = () => {
  const client = useQueryClient();
  const refresh = useRefreshBootstrap();
  return useMutation({
    mutationFn: (passwordEnabled: boolean) =>
      adminSettingsApi.updateAuth(passwordEnabled),
    onSuccess: (data) => {
      client.setQueryData(adminSettingsKeys.auth(), data);
      void refresh();
    },
  });
};

export const useUpdateSmtp = () => {
  const client = useQueryClient();
  const refresh = useRefreshBootstrap();
  return useMutation({
    mutationFn: (body: UpdateAdminSmtpRequest) =>
      adminSettingsApi.updateSmtp(body),
    onSuccess: (data) => {
      client.setQueryData(adminSettingsKeys.smtp(), data);
      void refresh();
    },
  });
};

export const useTestSmtp = () =>
  useMutation({
    mutationFn: (to: string | null) => adminSettingsApi.testSmtp(to),
  });

/** Провайдеры меняют и счётчик способов входа, и список на экране входа. */
const useProvidersChanged = () => {
  const client = useQueryClient();
  const refresh = useRefreshBootstrap();
  return () => {
    void client.invalidateQueries({ queryKey: adminSettingsKeys.providers() });
    void client.invalidateQueries({ queryKey: adminSettingsKeys.auth() });
    void refresh();
  };
};

export const useCreateProvider = () => {
  const changed = useProvidersChanged();
  return useMutation({
    mutationFn: (body: CreateAdminOidcProviderRequest) =>
      adminSettingsApi.createProvider(body),
    onSuccess: changed,
  });
};

export const useUpdateProvider = () => {
  const changed = useProvidersChanged();
  return useMutation({
    mutationFn: (input: { id: string; body: UpdateAdminOidcProviderRequest }) =>
      adminSettingsApi.updateProvider(input.id, input.body),
    onSuccess: changed,
  });
};

export const useDeleteProvider = () => {
  const changed = useProvidersChanged();
  return useMutation({
    mutationFn: (id: string) => adminSettingsApi.deleteProvider(id),
    onSuccess: changed,
  });
};
