import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { reviewApi } from "./reviewApi";
import type { NewThread, ThreadStatus } from "../model/review.schema";

export const reviewKeys = {
  all: ["review"] as const,
  threads: (projectId: string, path: string | null) =>
    [...reviewKeys.all, "threads", projectId, path] as const,
  project: (projectId: string) =>
    [...reviewKeys.all, "threads", projectId] as const,
  // Под ключом проекта: любая правка тредов обновляет и превью.
  document: (projectId: string, docId: string) =>
    [...reviewKeys.all, "threads", projectId, "document", docId] as const,
  mentions: (projectId: string, q: string) =>
    [...reviewKeys.all, "mentions", projectId, q] as const,
};

/** Без сессии совместной правки панель сама перечитывает треды раз в это время. */
export const REVIEW_POLL_MS = 15_000;

export const invalidateReview = (client: QueryClient, projectId: string) =>
  client.invalidateQueries({ queryKey: reviewKeys.project(projectId) });

export const useReviewThreads = (
  projectId: string,
  path: string | null,
  options: { enabled?: boolean; live?: boolean } = {},
) =>
  useQuery({
    queryKey: reviewKeys.threads(projectId, path),
    queryFn: ({ signal }) => reviewApi.threads(projectId, path, signal),
    enabled: options.enabled ?? true,
    // В сессии совместной правки обновление приходит событием сервера.
    refetchInterval: options.live ? false : REVIEW_POLL_MS,
    retry: false,
  });

export const useDocumentReview = (
  projectId: string,
  docId: string,
  options: { enabled?: boolean } = {},
) =>
  useQuery({
    queryKey: reviewKeys.document(projectId, docId),
    queryFn: ({ signal }) => reviewApi.documentReview(projectId, docId, signal),
    enabled: options.enabled ?? true,
    refetchInterval: REVIEW_POLL_MS,
    retry: false,
  });

export const useMentionCandidates = (
  projectId: string,
  q: string,
  enabled: boolean,
) =>
  useQuery({
    queryKey: reviewKeys.mentions(projectId, q),
    queryFn: ({ signal }) => reviewApi.mentions(projectId, q, signal),
    enabled,
    staleTime: 30_000,
    retry: false,
  });

const useAfterChange = (projectId: string) => {
  const client = useQueryClient();
  return () => invalidateReview(client, projectId);
};

export const useCreateThread = (projectId: string) => {
  const after = useAfterChange(projectId);
  return useMutation({
    mutationFn: (body: NewThread) => reviewApi.createThread(projectId, body),
    onSettled: after,
  });
};

export const useReplyToThread = (projectId: string) => {
  const after = useAfterChange(projectId);
  return useMutation({
    mutationFn: (v: { threadId: string; body: string; mentions: string[] }) =>
      reviewApi.reply(projectId, v.threadId, v.body, v.mentions),
    onSettled: after,
  });
};

export const useSetThreadStatus = (projectId: string) => {
  const after = useAfterChange(projectId);
  return useMutation({
    mutationFn: (v: { threadId: string; status: ThreadStatus }) =>
      reviewApi.setStatus(projectId, v.threadId, v.status),
    onSettled: after,
  });
};

export const useEditComment = (projectId: string) => {
  const after = useAfterChange(projectId);
  return useMutation({
    mutationFn: (v: { commentId: string; body: string }) =>
      reviewApi.editComment(projectId, v.commentId, v.body),
    onSettled: after,
  });
};

export const useDeleteComment = (projectId: string) => {
  const after = useAfterChange(projectId);
  return useMutation({
    mutationFn: (commentId: string) =>
      reviewApi.deleteComment(projectId, commentId),
    onSettled: after,
  });
};
