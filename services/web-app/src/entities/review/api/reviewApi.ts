import { apiClient, parseResp } from "@shared/api";
import {
  MentionCandidateListSchema,
  ReviewThreadListSchema,
  ReviewThreadSchema,
  type MentionCandidate,
  type NewThread,
  type ReviewThread,
  type ThreadStatus,
} from "../model/review.schema";

// Ошибки показывают сами формы (по коду из тела), общий тост клиента лишний.
const quiet = { silentError: true } as const;
const base = (projectId: string) =>
  `/projects/${encodeURIComponent(projectId)}/review`;

export const reviewApi = {
  threads: (
    projectId: string,
    path: string | null,
    signal?: AbortSignal,
  ): Promise<ReviewThread[]> =>
    apiClient
      .get(`${base(projectId)}/threads`, {
        ...quiet,
        params: path === null ? {} : { path },
        ...(signal ? { signal } : {}),
      })
      .then(parseResp(ReviewThreadListSchema))
      .then((page) => page.items),
  createThread: (projectId: string, body: NewThread): Promise<ReviewThread> =>
    apiClient
      .post(`${base(projectId)}/threads`, body, quiet)
      .then(parseResp(ReviewThreadSchema)),
  reply: (
    projectId: string,
    threadId: string,
    body: string,
    mentions: string[],
  ): Promise<ReviewThread> =>
    apiClient
      .post(
        `${base(projectId)}/threads/${encodeURIComponent(threadId)}/comments`,
        { body, mentions },
        quiet,
      )
      .then(parseResp(ReviewThreadSchema)),
  setStatus: (
    projectId: string,
    threadId: string,
    status: ThreadStatus,
  ): Promise<ReviewThread> =>
    apiClient
      .put(
        `${base(projectId)}/threads/${encodeURIComponent(threadId)}/status`,
        { status },
        quiet,
      )
      .then(parseResp(ReviewThreadSchema)),
  editComment: (
    projectId: string,
    commentId: string,
    body: string,
  ): Promise<ReviewThread> =>
    apiClient
      .patch(
        `${base(projectId)}/comments/${encodeURIComponent(commentId)}`,
        { body },
        quiet,
      )
      .then(parseResp(ReviewThreadSchema)),
  deleteComment: async (
    projectId: string,
    commentId: string,
  ): Promise<void> => {
    await apiClient.delete(
      `${base(projectId)}/comments/${encodeURIComponent(commentId)}`,
      quiet,
    );
  },
  mentions: (
    projectId: string,
    q: string,
    signal?: AbortSignal,
  ): Promise<MentionCandidate[]> =>
    apiClient
      .get(`${base(projectId)}/mentions`, {
        ...quiet,
        params: { q },
        ...(signal ? { signal } : {}),
      })
      .then(parseResp(MentionCandidateListSchema))
      .then((page) => page.items),
};
