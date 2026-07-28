import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { CreateSubmissionRequest } from "@shared/api/types";
import {
  submissionApi,
  type PreflightCustomFilesParams,
} from "./submissionApi";

type SubmissionRecord = Awaited<ReturnType<typeof submissionApi.create>>;
type ProfileList = Awaited<ReturnType<typeof submissionApi.getProfiles>>;
type SubmissionList = Awaited<ReturnType<typeof submissionApi.list>>;
type CustomFilePreflightResult = Awaited<
  ReturnType<typeof submissionApi.preflightCustomFiles>
>;

export const submissionKeys = {
  all: ["submissions"] as const,
  profiles: (projectId: string) =>
    [...submissionKeys.all, "profiles", projectId] as const,
  list: (projectId: string) =>
    [...submissionKeys.all, "list", projectId] as const,
};

export const useSubmissionProfiles = (projectId: string) =>
  useQuery<ProfileList>({
    queryKey: submissionKeys.profiles(projectId),
    queryFn: () => submissionApi.getProfiles(projectId),
    enabled: !!projectId,
  });

export const useSubmissions = (projectId: string) =>
  useQuery<SubmissionList>({
    queryKey: submissionKeys.list(projectId),
    queryFn: () => submissionApi.list(projectId),
    enabled: !!projectId,
  });

export const useCreateSubmission = () => {
  const queryClient = useQueryClient();
  return useMutation<
    SubmissionRecord,
    Error,
    { projectId: string; data: CreateSubmissionRequest }
  >({
    mutationFn: ({ projectId, data }) => submissionApi.create(projectId, data),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: submissionKeys.list(projectId),
      });
    },
  });
};

// Triggered on click (before the actual create-submission call), not on
// mount — a preflight check makes sense only right before packaging.
export const useSubmissionCustomFilePreflight = () =>
  useMutation<
    CustomFilePreflightResult,
    Error,
    { projectId: string; params: PreflightCustomFilesParams }
  >({
    mutationFn: ({ projectId, params }) =>
      submissionApi.preflightCustomFiles(projectId, params),
  });
