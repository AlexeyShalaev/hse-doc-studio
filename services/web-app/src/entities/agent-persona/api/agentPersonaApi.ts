import { apiClient, parseResp } from "@shared/api";
import {
  AgentPersonaListSchema,
  AgentPersonaSchema,
  BuiltinPersonaListSchema,
  type CreateAgentPersonaInput,
  type UpdateAgentPersonaInput,
} from "../model/agentPersona.schema";

export const agentPersonaApi = {
  list: () =>
    apiClient.get(`/agent-personas`).then(parseResp(AgentPersonaListSchema)),

  builtins: () =>
    apiClient
      .get(`/agent-personas/builtins`)
      .then(parseResp(BuiltinPersonaListSchema)),

  create: (body: CreateAgentPersonaInput) =>
    apiClient.post(`/agent-personas`, body).then(parseResp(AgentPersonaSchema)),

  update: (id: string, body: UpdateAgentPersonaInput) =>
    apiClient
      .patch(`/agent-personas/${id}`, body)
      .then(parseResp(AgentPersonaSchema)),

  remove: (id: string) =>
    apiClient.delete(`/agent-personas/${id}`).then(() => id),
};
