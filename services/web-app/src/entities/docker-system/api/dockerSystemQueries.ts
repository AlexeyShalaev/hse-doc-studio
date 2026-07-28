import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  dockerSystemApi,
  isJobActive,
  type CleanupJob,
  type CleanupJobState,
  type DockerCleanupInput,
  type DockerUsage,
} from "./dockerSystemApi";

const JOB_POLL_INTERVAL_MS = 1000;

export const dockerSystemKeys = {
  all: ["docker-system"] as const,
  usage: () => [...dockerSystemKeys.all, "usage"] as const,
  cleanupJob: () => [...dockerSystemKeys.all, "cleanup-job"] as const,
};

export const useDockerUsage = () =>
  useQuery<DockerUsage>({
    queryKey: dockerSystemKeys.usage(),
    queryFn: () => dockerSystemApi.usage(),
    // `docker system df -v` walks every image/container/volume — not cheap
    // enough to poll aggressively, but fresh enough that reopening Settings
    // or the startup check doesn't show minutes-stale numbers.
    staleTime: 60_000,
  });

/**
 * The one cleanup job (running or last finished). Polls every second while a
 * job is active, then stops; the usage query is refreshed when the job leaves
 * the active state (see the mutation + component effects).
 */
export const useCleanupJob = () =>
  useQuery<CleanupJobState>({
    queryKey: dockerSystemKeys.cleanupJob(),
    queryFn: () => dockerSystemApi.cleanupJob(),
    refetchInterval: (query) =>
      isJobActive(query.state.data?.job) ? JOB_POLL_INTERVAL_MS : false,
  });

export const useStartCleanup = () => {
  const queryClient = useQueryClient();
  return useMutation<CleanupJob, Error, DockerCleanupInput>({
    mutationFn: (input) => dockerSystemApi.startCleanup(input),
    onSuccess: (job) => {
      // Seed the job cache so polling kicks in immediately (no 1s blind spot).
      queryClient.setQueryData<CleanupJobState>(dockerSystemKeys.cleanupJob(), {
        job,
      });
    },
  });
};

export const useCancelCleanup = () => {
  const queryClient = useQueryClient();
  return useMutation<CleanupJobState>({
    mutationFn: () => dockerSystemApi.cancelCleanup(),
    onSuccess: (state) => {
      queryClient.setQueryData(dockerSystemKeys.cleanupJob(), state);
    },
  });
};
