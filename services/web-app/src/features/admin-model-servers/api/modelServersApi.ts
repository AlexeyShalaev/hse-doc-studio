import { adminClient, parseResp } from "@shared/api";
import {
  CapabilitiesSchema,
  CatalogSchema,
  EstimateSchema,
  LogsSchema,
  ModelServerListSchema,
  ModelServerSchema,
  type Capabilities,
  type CatalogModel,
  type Engine,
  type Estimate,
  type InstallRequest,
  type ModelServer,
} from "./schemas";

// Ошибки показывает сам экран по коду: тост не нужен.
const quiet = { silentError: true } as const;
const base = "/model-servers";

export const modelServersApi = {
  capabilities: (): Promise<Capabilities> =>
    adminClient
      .get(`${base}/capabilities`, quiet)
      .then(parseResp(CapabilitiesSchema)),
  catalog: (engine: Engine, q: string): Promise<CatalogModel[]> =>
    adminClient
      .get(`${base}/catalog`, { ...quiet, params: { engine, q } })
      .then(parseResp(CatalogSchema))
      .then((r) => r.items),
  estimate: (engine: Engine, model: string): Promise<Estimate> =>
    adminClient
      .post(`${base}/estimate`, { engine, model }, quiet)
      .then(parseResp(EstimateSchema)),
  list: (): Promise<ModelServer[]> =>
    adminClient
      .get(base, quiet)
      .then(parseResp(ModelServerListSchema))
      .then((r) => r.items),
  install: (body: InstallRequest): Promise<ModelServer> =>
    adminClient.post(base, body, quiet).then(parseResp(ModelServerSchema)),
  logs: (id: string): Promise<string> =>
    adminClient
      .get(`${base}/${id}/logs`, { ...quiet, params: { tail: 300 } })
      .then(parseResp(LogsSchema))
      .then((r) => r.text),
  start: (id: string): Promise<ModelServer> =>
    adminClient
      .post(`${base}/${id}/start`, undefined, quiet)
      .then(parseResp(ModelServerSchema)),
  stop: (id: string): Promise<ModelServer> =>
    adminClient
      .post(`${base}/${id}/stop`, undefined, quiet)
      .then(parseResp(ModelServerSchema)),
  remove: async (id: string, purgeModels: boolean): Promise<void> => {
    await adminClient.delete(`${base}/${id}`, {
      ...quiet,
      params: { purge_models: purgeModels },
    });
  },
};
