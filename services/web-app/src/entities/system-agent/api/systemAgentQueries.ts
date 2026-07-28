import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ChatSession,
  ChatSessionDetail,
  CreateChatSessionInput,
  Persona,
  StartTurnInput,
  UpdateChatSessionInput,
} from "@entities/agent-chat";
import { systemAgentApi } from "./systemAgentApi";

export const systemAgentKeys = {
  all: ["system-agent"] as const,
  list: () => [...systemAgentKeys.all, "list"] as const,
  detail: (sessionId: string) =>
    [...systemAgentKeys.all, "detail", sessionId] as const,
  personas: () => [...systemAgentKeys.all, "personas"] as const,
};

export const useSystemChats = () =>
  useQuery<ChatSession[]>({
    queryKey: systemAgentKeys.list(),
    queryFn: () => systemAgentApi.list(),
  });

// Selectable agent roles. Static for a session, so cache them aggressively.
export const useAgentPersonas = () =>
  useQuery<Persona[]>({
    queryKey: systemAgentKeys.personas(),
    queryFn: () => systemAgentApi.personas(),
    staleTime: Infinity,
  });

export const useSystemChat = (sessionId: string | null) =>
  useQuery<ChatSessionDetail>({
    queryKey: systemAgentKeys.detail(sessionId ?? ""),
    queryFn: () => systemAgentApi.get(sessionId ?? ""),
    enabled: !!sessionId,
  });

export const useCreateSystemChat = () => {
  const queryClient = useQueryClient();
  return useMutation<ChatSession, Error, CreateChatSessionInput>({
    mutationFn: (body) => systemAgentApi.create(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: systemAgentKeys.list() });
    },
  });
};

export const useRenameSystemChat = () => {
  const queryClient = useQueryClient();
  return useMutation<ChatSession, Error, { sessionId: string; title: string }>({
    mutationFn: ({ sessionId, title }) =>
      systemAgentApi.rename(sessionId, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: systemAgentKeys.list() });
    },
  });
};

export const useUpdateSystemChat = () => {
  const queryClient = useQueryClient();
  return useMutation<
    ChatSession,
    Error,
    { sessionId: string; body: UpdateChatSessionInput }
  >({
    mutationFn: ({ sessionId, body }) => systemAgentApi.update(sessionId, body),
    onSuccess: (_data, { sessionId }) => {
      void queryClient.invalidateQueries({ queryKey: systemAgentKeys.list() });
      void queryClient.invalidateQueries({
        queryKey: systemAgentKeys.detail(sessionId),
      });
    },
  });
};

export const useDeleteSystemChat = () => {
  const queryClient = useQueryClient();
  return useMutation<string, Error, string>({
    mutationFn: (sessionId) => systemAgentApi.remove(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: systemAgentKeys.list() });
    },
  });
};

export const useStartSystemTurn = () =>
  useMutation<
    { run_id: string; user_message_seq: number },
    Error,
    { sessionId: string; body: StartTurnInput }
  >({
    mutationFn: ({ sessionId, body }) =>
      systemAgentApi.startTurn(sessionId, body),
  });

export const useApproveSystemTurn = () =>
  useMutation<
    { run_id: string; user_message_seq: number },
    Error,
    { sessionId: string; runId: string; callIds: string[] }
  >({
    mutationFn: ({ sessionId, runId, callIds }) =>
      systemAgentApi.approveTurn(sessionId, runId, callIds),
  });

export const useAnswerSystemTurn = () =>
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
      systemAgentApi.answerTurn(sessionId, runId, answers),
  });

export const useCancelSystemTurn = () =>
  useMutation<
    { cancelled_task: boolean; record_finalized: boolean },
    Error,
    { sessionId: string; runId: string }
  >({
    mutationFn: ({ sessionId, runId }) =>
      systemAgentApi.cancelTurn(sessionId, runId),
  });
