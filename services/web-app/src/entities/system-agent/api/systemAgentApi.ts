import { z } from "zod";
import {
  CancelTurnResponseSchema,
  ChatSessionDetailSchema,
  ChatSessionSchema,
  PersonaListSchema,
  StartTurnResponseSchema,
  type CreateChatSessionInput,
  type StartTurnInput,
  type UpdateChatSessionInput,
} from "@entities/agent-chat";
import { apiClient, parseResp } from "@shared/api";

// The system (no-project) agent reuses the chat response shapes, only the URLs
// differ: /agent/chats... instead of /projects/<id>/chats...
const ChatSessionListSchema = z.array(ChatSessionSchema);

export const systemAgentApi = {
  list: () =>
    apiClient.get(`/agent/chats`).then(parseResp(ChatSessionListSchema)),

  get: (sessionId: string) =>
    apiClient
      .get(`/agent/chats/${sessionId}`)
      .then(parseResp(ChatSessionDetailSchema)),

  personas: () =>
    apiClient.get(`/agent/personas`).then(parseResp(PersonaListSchema)),

  create: (body: CreateChatSessionInput) =>
    apiClient.post(`/agent/chats`, body).then(parseResp(ChatSessionSchema)),

  rename: (sessionId: string, title: string) =>
    apiClient
      .patch(`/agent/chats/${sessionId}`, { title })
      .then(parseResp(ChatSessionSchema)),

  // Partial update (e.g. change the agent role) — same PATCH endpoint as rename.
  update: (sessionId: string, body: UpdateChatSessionInput) =>
    apiClient
      .patch(`/agent/chats/${sessionId}`, body)
      .then(parseResp(ChatSessionSchema)),

  remove: (sessionId: string) =>
    apiClient.delete(`/agent/chats/${sessionId}`).then(() => sessionId),

  startTurn: (sessionId: string, body: StartTurnInput) =>
    apiClient
      .post(`/agent/chats/${sessionId}/turns`, body)
      .then(parseResp(StartTurnResponseSchema)),

  approveTurn: (sessionId: string, runId: string, callIds: string[]) =>
    apiClient
      .post(`/agent/chats/${sessionId}/runs/${runId}/approve`, {
        call_ids: callIds,
      })
      .then(parseResp(StartTurnResponseSchema)),

  answerTurn: (
    sessionId: string,
    runId: string,
    answers: Record<string, Record<string, string>>,
  ) =>
    apiClient
      .post(`/agent/chats/${sessionId}/runs/${runId}/answer`, { answers })
      .then(parseResp(StartTurnResponseSchema)),

  cancelTurn: (sessionId: string, runId: string) =>
    apiClient
      .post(`/agent/chats/${sessionId}/runs/${runId}/cancel`)
      .then(parseResp(CancelTurnResponseSchema)),

  // Relative path → same-origin (Vite proxy / all-in-one), consumed by EventSource.
  streamUrl: (sessionId: string, runId: string): string =>
    `/api/v1/agent/chats/${sessionId}/runs/${runId}/stream`,
};
