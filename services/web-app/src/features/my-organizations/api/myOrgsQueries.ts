import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sessionKeys } from "@entities/session";
import { myOrgsApi } from "./myOrgsApi";

export const myOrgsKeys = {
  all: ["my-orgs"] as const,
  list: () => [...myOrgsKeys.all, "list"] as const,
};

export const useMyOrgs = () =>
  useQuery({
    queryKey: myOrgsKeys.list(),
    queryFn: () => myOrgsApi.list(),
    staleTime: 30_000,
  });

export const useLeaveOrg = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => myOrgsApi.leave(slug),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: myOrgsKeys.all });
      // Роли в организациях приходят в bootstrap: меню и доступ к админке обновятся.
      void client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });
    },
  });
};
