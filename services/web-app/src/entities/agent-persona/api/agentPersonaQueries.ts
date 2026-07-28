import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentPersonaApi } from "./agentPersonaApi";
import type {
  AgentPersona,
  BuiltinPersona,
  CreateAgentPersonaInput,
  UpdateAgentPersonaInput,
} from "../model/agentPersona.schema";

export const agentPersonaKeys = {
  all: ["agent-personas"] as const,
  lists: () => [...agentPersonaKeys.all, "list"] as const,
  builtins: () => [...agentPersonaKeys.all, "builtins"] as const,
};

// The chat picker reads the MERGED selectable list from the system-agent entity
// (key ["system-agent", "personas"], staleTime Infinity). Referenced here by its
// literal array — FSD forbids an entity importing another entity's key factory —
// so a CRUD change refreshes the picker too.
const SELECTABLE_PERSONAS_KEY = ["system-agent", "personas"] as const;

export const useCustomPersonas = () =>
  useQuery<AgentPersona[]>({
    queryKey: agentPersonaKeys.lists(),
    queryFn: () => agentPersonaApi.list(),
    staleTime: 60_000,
  });

export const useBuiltinPersonas = () =>
  useQuery<BuiltinPersona[]>({
    queryKey: agentPersonaKeys.builtins(),
    queryFn: () => agentPersonaApi.builtins(),
    staleTime: Infinity,
  });

const useInvalidatePersonas = () => {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: agentPersonaKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: SELECTABLE_PERSONAS_KEY });
  };
};

export const useCreatePersona = () => {
  const invalidate = useInvalidatePersonas();
  return useMutation<AgentPersona, Error, CreateAgentPersonaInput>({
    mutationFn: (body) => agentPersonaApi.create(body),
    onSuccess: invalidate,
  });
};

export const useUpdatePersona = () => {
  const invalidate = useInvalidatePersonas();
  return useMutation<
    AgentPersona,
    Error,
    { id: string; body: UpdateAgentPersonaInput }
  >({
    mutationFn: ({ id, body }) => agentPersonaApi.update(id, body),
    onSuccess: invalidate,
  });
};

export const useDeletePersona = () => {
  const invalidate = useInvalidatePersonas();
  return useMutation<string, Error, string>({
    mutationFn: (id) => agentPersonaApi.remove(id),
    onSuccess: invalidate,
  });
};
