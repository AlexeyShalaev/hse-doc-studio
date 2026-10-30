import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import { MyOrgSchema, type MyOrg } from "@entities/session";

// Ошибки показывает сам раздел: тост не нужен.
const quiet = { silentError: true } as const;

export const myOrgsApi = {
  list: (): Promise<MyOrg[]> =>
    apiClient.get("/account/orgs", quiet).then(parseResp(z.array(MyOrgSchema))),
  leave: async (slug: string): Promise<void> => {
    await apiClient.delete(
      `/account/orgs/${encodeURIComponent(slug)}/membership`,
      quiet,
    );
  },
};
