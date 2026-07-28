import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentChatApi } from "./agentChatApi";
import type {
  AgentTool,
  ChatSession,
  ChatSessionDetail,
  CreateChatSessionInput,
  StartTurnInput,
} from "../model/agentChat.schema";

export const agentChatKeys = {
  all: ["agent-chat"] as const,
  list: (projectId: string) =>
    [...agentChatKeys.all, "list", projectId] as const,
  detail: (projectId: string, sessionId: string) =>
    [...agentChatKeys.all, "detail", projectId, sessionId] as const,
  tools: () => [...agentChatKeys.all, "tools"] as const,
};

// The tool catalog is static for the app session — cache it indefinitely.
export const useAgentTools = () =>
  useQuery<AgentTool[]>({
    queryKey: agentChatKeys.tools(),
    queryFn: () => agentChatApi.listTools(),
    staleTime: Infinity,
  });

export const useChatSessions = (projectId: string) =>
  useQuery<ChatSession[]>({
    queryKey: agentChatKeys.list(projectId),
    queryFn: () => agentChatApi.list(projectId),
    enabled: !!projectId,
  });

export const useChatSession = (projectId: string, sessionId: string | null) =>
  useQuery<ChatSessionDetail>({
    queryKey: agentChatKeys.detail(projectId, sessionId ?? ""),
    queryFn: () => agentChatApi.get(projectId, sessionId ?? ""),
    enabled: !!projectId && !!sessionId,
  });

export const useCreateChatSession = (projectId: string) => {
  const queryClient = useQueryClient();
  return useMutation<ChatSession, Error, CreateChatSessionInput>({
    mutationFn: (body) => agentChatApi.create(projectId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: agentChatKeys.list(projectId),
      });
    },
  });
};

export const useRenameChatSession = (projectId: string) => {
  const queryClient = useQueryClient();
  return useMutation<ChatSession, Error, { sessionId: string; title: string }>({
    mutationFn: ({ sessionId, title }) =>
      agentChatApi.rename(projectId, sessionId, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: agentChatKeys.list(projectId),
      });
    },
  });
};

export const useDeleteChatSession = (projectId: string) => {
  const queryClient = useQueryClient();
  return useMutation<string, Error, string>({
    mutationFn: (sessionId) => agentChatApi.remove(projectId, sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: agentChatKeys.list(projectId),
      });
    },
  });
};

export const useStartTurn = (projectId: string) =>
  useMutation<
    { run_id: string; user_message_seq: number },
    Error,
    { sessionId: string; body: StartTurnInput }
  >({
    mutationFn: ({ sessionId, body }) =>
      agentChatApi.startTurn(projectId, sessionId, body),
  });

export const useApproveTurn = (projectId: string) =>
  useMutation<
    { run_id: string; user_message_seq: number },
    Error,
    { sessionId: string; runId: string; callIds: string[] }
  >({
    mutationFn: ({ sessionId, runId, callIds }) =>
      agentChatApi.approveTurn(projectId, sessionId, runId, callIds),
  });

export const useAnswerTurn = (projectId: string) =>
  useMutation<
    { run_id: string; user_message_seq: number },
    Error,
    {
      sessionId: string;
      runId: string;
      answers: Record<string, Record<string, string>>;
    }
  >({
    mutationFn: ({ sessionId, runId, answers }) =>
      agentChatApi.answerTurn(projectId, sessionId, runId, answers),
  });

export const useCancelTurn = (projectId: string) =>
  useMutation<
    { cancelled_task: boolean; record_finalized: boolean },
    Error,
    { sessionId: string; runId: string }
  >({
    mutationFn: ({ sessionId, runId }) =>
      agentChatApi.cancelTurn(projectId, sessionId, runId),
  });
