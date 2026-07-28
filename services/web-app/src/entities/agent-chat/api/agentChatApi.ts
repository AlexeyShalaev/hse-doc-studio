import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import {
  AgentToolSchema,
  CancelTurnResponseSchema,
  ChatSessionDetailSchema,
  ChatSessionSchema,
  StartTurnResponseSchema,
  type CreateChatSessionInput,
  type StartTurnInput,
} from "../model/agentChat.schema";

const ChatSessionListSchema = z.array(ChatSessionSchema);
const AgentToolListSchema = z.array(AgentToolSchema);

export const agentChatApi = {
  list: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/chats`)
      .then(parseResp(ChatSessionListSchema)),

  // Project-independent: the agent's tool catalog for the Configure-Tools UI.
  listTools: () =>
    apiClient.get(`/agent/tools`).then(parseResp(AgentToolListSchema)),

  get: (projectId: string, sessionId: string) =>
    apiClient
      .get(`/projects/${projectId}/chats/${sessionId}`)
      .then(parseResp(ChatSessionDetailSchema)),

  create: (projectId: string, body: CreateChatSessionInput) =>
    apiClient
      .post(`/projects/${projectId}/chats`, body)
      .then(parseResp(ChatSessionSchema)),

  rename: (projectId: string, sessionId: string, title: string) =>
    apiClient
      .patch(`/projects/${projectId}/chats/${sessionId}`, { title })
      .then(parseResp(ChatSessionSchema)),

  remove: (projectId: string, sessionId: string) =>
    apiClient
      .delete(`/projects/${projectId}/chats/${sessionId}`)
      .then(() => sessionId),

  startTurn: (projectId: string, sessionId: string, body: StartTurnInput) =>
    apiClient
      .post(`/projects/${projectId}/chats/${sessionId}/turns`, body)
      .then(parseResp(StartTurnResponseSchema)),

  approveTurn: (
    projectId: string,
    sessionId: string,
    runId: string,
    callIds: string[],
  ) =>
    apiClient
      .post(`/projects/${projectId}/chats/${sessionId}/runs/${runId}/approve`, {
        call_ids: callIds,
      })
      .then(parseResp(StartTurnResponseSchema)),

  answerTurn: (
    projectId: string,
    sessionId: string,
    runId: string,
    answers: Record<string, Record<string, string>>,
  ) =>
    apiClient
      .post(`/projects/${projectId}/chats/${sessionId}/runs/${runId}/answer`, {
        answers,
      })
      .then(parseResp(StartTurnResponseSchema)),

  cancelTurn: (projectId: string, sessionId: string, runId: string) =>
    apiClient
      .post(`/projects/${projectId}/chats/${sessionId}/runs/${runId}/cancel`)
      .then(parseResp(CancelTurnResponseSchema)),

  // Relative path → same-origin (Vite proxy in dev, all-in-one in prod), like the
  // compile stream. Consumed by an EventSource in the feature layer.
  streamUrl: (projectId: string, sessionId: string, runId: string): string =>
    `/api/v1/projects/${projectId}/chats/${sessionId}/runs/${runId}/stream`,
};
